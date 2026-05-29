"""HermesBench v2 use-case suites — one per category.

For each case in a category, a Codex evaluator driver orchestrates a target
adapter against a driver/target-agnostic scenario. Target selection is run
configuration. Scoring is evidence-grounded: mechanical signals, artifact
checks, scope checks, latency, and bounded LLM judgement determine whether the
scenario reached a real outcome and whether that outcome fulfilled the request.

The final score is the only verdict. Outcome, stability, scope, evidence checks,
responsiveness, and judged fulfillment are folded into the score, so a
correct-looking but non-closing or artifact-wrong turn cannot hide behind a high
average.

All suites self-skip without HERMES_RUN_LLM_EVALS (they drive real agents).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from hermesbench import checks, drivers, scenarios, scoring, targets, usecases
from hermesbench import judge as judge_mod

TRIALS = int(os.environ.get("HERMES_BENCH_TRIALS", "2"))
CONCURRENCY = int(os.environ.get("HERMES_BENCH_CONCURRENCY", "4"))
_PII_PATTERNS = (
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("phone", r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"),
    ("token", r"(?i)\b(?:sk|ghp|gho|xoxb|xoxp|AKIA)[A-Za-z0-9_\-]{12,}\b"),
)


def _redact_pii_text(value) -> str | None:
    if value is None:
        return None
    import re

    text = str(value)
    for label, pattern in _PII_PATTERNS:
        text = re.sub(pattern, f"<redacted:{label}>", text)
    return text


def _public_observability(mech: dict) -> dict:
    obs = mech.get("observability") if isinstance(mech.get("observability"), dict) else {}
    tools = [
        {
            "name": item.get("name"),
            "source": item.get("source"),
            "status": item.get("status"),
            "args_retention": item.get("args_retention", "omitted_public_safe"),
            "result_retention": item.get("result_retention", "omitted_public_safe"),
        }
        for item in (obs.get("tools") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    return {
        "sources": obs.get("sources") or {},
        "session_id": obs.get("session_id"),
        "turn": obs.get("turn") or {},
        "spans": (obs.get("spans") or [])[:25],
        "tools": tools,
        "skills": obs.get("skills") or [],
        "messages": obs.get("messages") or {},
        "trajectory": obs.get("trajectory") or {},
        "kanban": obs.get("kanban") or {},
        "retention": obs.get("retention") or {},
    }


def _responsiveness(ttfa_ms, wall_ms, reply_target_s: float) -> float:
    """0..1 time-to-reply score: full credit at/under target, linear decay to 0 at 3×.

    Prefers telemetry ttfa_ms (true first-answer latency) when present; in the
    one-shot `chat -q` harness that's usually absent, so it falls back to
    wall-clock (total time to the single reply).
    """
    t_ms = ttfa_ms if ttfa_ms is not None else wall_ms
    if t_ms is None:
        return 0.0
    t = t_ms / 1000.0
    budget = max(0.1, reply_target_s)
    if t <= budget:
        return 1.0
    return max(0.0, 1.0 - (t - budget) / (2.0 * budget))


def _p50(xs: list[float]):
    vals = sorted(v for v in xs if v is not None)
    return vals[len(vals) // 2] if vals else None


def _run_trial(case: dict, b: dict) -> dict:
    scenario = scenarios.from_case(case)
    timeout_s = int(b["conclude_s"]) + 30
    target = targets.build_target()
    m = drivers.run(scenario, target, timeout_s=timeout_s)
    transcript = m.get("transcript") or []

    judge_case = dict(case)
    judge_case["prompt"] = scenarios.prompt_for_judge(scenario)
    judge_case["success_criteria"] = scenario.get("success_criteria") or case.get("success_criteria") or []
    judge_case["safety_criteria"] = scenario.get("safety_criteria") or case.get("safety_criteria") or []
    judge_case["observability"] = m.get("observability") or {}
    v = judge_mod.judge(judge_case, m["reply"], transcript=transcript if len(transcript) > 1 else None)
    check_result = checks.run_checks(scenario, m)
    resp = _responsiveness(m.get("ttfa_ms"), m.get("wall_ms"), b["reply_target_s"])
    driver_decision = m.get("driver_decision") if isinstance(m.get("driver_decision"), dict) else {}
    driver_closed = driver_decision.get("scenario_closed")
    scoring_execution = dict(m)
    if driver_closed is False:
        scoring_execution["concluded"] = False
    scored = scoring.score_case(
        execution=scoring_execution,
        check_result=check_result,
        judge=v,
        responsiveness=resp,
    )
    genuine_conclusion = bool(m["concluded"]) and v["conclusion_type"] != "none"
    if driver_closed is not None:
        genuine_conclusion = genuine_conclusion and bool(driver_closed)
    return {
        "case": case["id"],
        "expectation": case.get("expectation"),
        "turn_count": len(scenario["turns"]),
        "scenario": {
            "driver": (m.get("driver") or {}).get("kind", "codex"),
            "target": m.get("target") or getattr(target, "describe", lambda: {})(),
            "capabilities": scenario.get("capabilities") or {},
            "checks": len(scenario.get("checks") or []),
        },
        "mech": m,
        "judge": v,
        "checks": check_result,
        "driver_decision": driver_decision,
        "genuine_conclusion": genuine_conclusion,
        "responsiveness": resp,
        "score": scored,
    }


def _redacted_case_result(r: dict) -> dict:
    """Public-safe per-trial observation for run artifacts.

    A redacted public transcript is kept by default so published leaderboard
    evidence is reviewable. Unredacted raw replies/transcripts, controller
    stdout/stderr,
    and local artifact paths are not published by default because they can
    contain user-private context or environment-specific details.
    """
    mech = r.get("mech") or {}
    driver = mech.get("driver") or {}
    scored = r.get("score") or {}
    judge = r.get("judge") or {}
    checks = r.get("checks") or {}
    side_effects = mech.get("side_effects") or {}
    public_obs = _public_observability(mech)
    include_raw_trace = os.environ.get("HERMES_BENCH_INCLUDE_RAW_TRACES", "").lower() in {
        "1", "true", "yes", "on",
    }
    public_transcript = [
        {
            "turn": t.get("turn"),
            "user": _redact_pii_text(t.get("user")),
            "assistant": _redact_pii_text(t.get("assistant")),
            "error": _redact_pii_text(t.get("error")),
            "timed_out": t.get("timed_out"),
            "wall_ms": t.get("wall_ms"),
        }
        for t in (mech.get("transcript") or [])
    ]
    out = {
        "case": r.get("case"),
        "expectation": r.get("expectation"),
        "turn_count": r.get("turn_count"),
        "scenario": r.get("scenario") or {},
        "score": round(float(scored.get("score") or 0.0), 2),
        "base_score": round(float(scored.get("base_score") or 0.0), 2),
        "balanced_score": round(float(scored.get("balanced_score") or 0.0), 2),
        "axes": {
            k: round(100.0 * float(v), 1)
            for k, v in (scored.get("axes") or {}).items()
        },
        "top_axes": {
            k: round(100.0 * float(v), 1)
            for k, v in (scored.get("top_axes") or {}).items()
        },
        "balance_factor": round(float(scored.get("balance_factor") or 0.0), 3),
        "mechanical": {
            "responded": bool(mech.get("responded")),
            "concluded": bool(mech.get("concluded")),
            "stable": bool(mech.get("stable")),
            "timed_out": bool(mech.get("timed_out")),
            "turns_sent": driver.get("turns_sent", mech.get("turn_count", 0)),
            "turn_budget": driver.get("max_turns", r.get("turn_count")),
            "ttfa_ms": mech.get("ttfa_ms"),
            "ttlt_ms": mech.get("ttlt_ms"),
            "wall_ms": mech.get("wall_ms"),
        },
        "driver_decision": {
            k: (v[:240] if isinstance(v, str) else v)
            for k, v in (r.get("driver_decision") or {}).items()
            if k in {"scenario_closed", "closure_type", "turns_sent", "reason"}
        },
        "judge": {
            "conclusion_type": judge.get("conclusion_type"),
            "appropriate": judge.get("appropriate"),
            "coherent": judge.get("coherent"),
            "judge_error": judge.get("judge_error"),
            "reason": str(judge.get("reason") or "")[:240],
        },
        "checks": {
            "explicit_count": checks.get("explicit_count"),
            "score": checks.get("score"),
            "scope_ok": checks.get("scope_ok"),
            "failed": [
                c for c in (checks.get("checks") or [])
                if not c.get("ok")
            ][:5],
        },
        "side_effects": {
            "scope": side_effects.get("scope"),
            "total_files": side_effects.get("total_files", 0),
            "total_bytes": side_effects.get("total_bytes", 0),
            "files": [
                {
                    "path": f.get("path"),
                    "bytes": f.get("bytes"),
                    "sha256_16": f.get("sha256_16"),
                }
                for f in (side_effects.get("files") or [])[:10]
            ],
        },
        "observability": public_obs,
        "used_tools": sorted({item["name"] for item in public_obs.get("tools") or [] if item.get("name")}),
        "used_skills": sorted(str(item) for item in (public_obs.get("skills") or []) if item),
        "trace_retention": {
            "public_transcript": "included_pii_redacted",
            "raw_target_reply": "included_private_opt_in" if include_raw_trace else "omitted_public_safe",
            "raw_transcript": "included_private_opt_in" if include_raw_trace else "omitted_public_safe",
            "controller_output": "omitted_public_safe",
            "local_artifact_paths": "redacted_to_scoped_manifest",
        },
        "public_transcript": public_transcript,
    }
    if include_raw_trace:
        out["raw_transcript"] = [
            {
                "turn": t.get("turn"),
                "user": t.get("user"),
                "assistant": t.get("assistant"),
                "error": t.get("error"),
                "timed_out": t.get("timed_out"),
                "wall_ms": t.get("wall_ms"),
            }
            for t in (mech.get("transcript") or [])
        ]
        out["raw_target_reply"] = mech.get("reply")
    return out


def _run_cases(cases: list[dict], *, category: str) -> dict:
    if not os.environ.get("HERMES_RUN_LLM_EVALS"):
        return {"skipped": True, "skip_reason": "HERMES_RUN_LLM_EVALS not set"}

    b = usecases.budget(category)
    if not cases:
        return {"skipped": True, "skip_reason": f"no cases for {category}"}

    jobs = [c for c in cases for _ in range(TRIALS)]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, CONCURRENCY)) as pool:
        futs = [pool.submit(_run_trial, c, b) for c in jobs]
        for f in as_completed(futs):
            results.append(f.result())

    n = len(results) or 1
    mechanical_closure_rate = sum(1 for r in results if r["mech"]["concluded"]) / n
    outcome_mean = sum(r["score"]["axes"]["outcome_reached"] for r in results) / n
    stable_rate = sum(1 for r in results if r["mech"]["stable"]) / n
    responded_rate = sum(1 for r in results if r["mech"]["responded"]) / n
    driver_decisions = [r["driver_decision"] for r in results if r["driver_decision"]]
    driver_closed_rate = (
        sum(1 for d in driver_decisions if d.get("scenario_closed")) / len(driver_decisions)
        if driver_decisions else None
    )
    resp_mean = sum(r["responsiveness"] for r in results) / n
    evidence_mean = sum(r["score"]["axes"]["evidence_truthfulness"] for r in results) / n
    runtime_scope_mean = sum(r["score"]["axes"]["runtime_scope_safety"] for r in results) / n
    scope_mean = sum(r["score"]["axes"]["scope_discipline"] for r in results) / n

    judged = [r for r in results if not r["judge"]["judge_error"]]
    fulfillment_mean = (
        sum(r["score"]["axes"]["task_fulfillment"] for r in judged) / len(judged)
    ) if judged else 0.0
    communication_mean = (
        sum(r["score"]["axes"]["communication_quality"] for r in judged) / len(judged)
    ) if judged else 0.0
    top_axis_means = {
        "capability_truthfulness": sum(
            r["score"]["top_axes"]["capability_truthfulness"] for r in results
        ) / n,
        "reliability_safety": sum(r["score"]["top_axes"]["reliability_safety"] for r in results) / n,
        "efficiency_ux": sum(r["score"]["top_axes"]["efficiency_ux"] for r in results) / n,
    }
    score = sum(r["score"]["score"] for r in results) / n
    base_score = sum(r["score"]["base_score"] for r in results) / n
    balanced_score = sum(r["score"]["balanced_score"] for r in results) / n
    balance_factor_mean = sum(r["score"]["balance_factor"] for r in results) / n

    ctypes: dict = {}
    for r in results:
        ct = r["judge"]["conclusion_type"]
        ctypes[ct] = ctypes.get(ct, 0) + 1

    # A short sample of what went wrong, for the run JSON.
    failures = [
        {"case": r["case"], "conclusion": r["judge"]["conclusion_type"],
         "stable": r["mech"]["stable"], "reason": r["judge"]["reason"][:160]}
        for r in results
        if not r["genuine_conclusion"] or not r["mech"]["stable"]
    ][:5]

    side_effect_trials = [r for r in results if (r["mech"].get("side_effects") or {}).get("total_files", 0) > 0]
    side_effect_samples = []
    for r in side_effect_trials[:5]:
        manifest = r["mech"].get("side_effects") or {}
        side_effect_samples.append({
            "case": r["case"],
            "scope": manifest.get("scope"),
            "total_files": manifest.get("total_files", 0),
            "total_bytes": manifest.get("total_bytes", 0),
            "files": (manifest.get("files") or [])[:5],
            "artifact_home": r["mech"].get("artifact_home"),
        })

    return {
        "score": round(score, 2),
        "metrics": {
            "trials": n,
            "cases": len(cases),
            "turns_planned": sum(len(usecases.case_turns(c)) for c in cases) * TRIALS,
            "driver_turn_budget": sum(
                (r["mech"].get("driver") or {}).get("max_turns", r["turn_count"])
                for r in results
            ),
            "turns_sent": sum(
                (r["mech"].get("driver") or {}).get("turns_sent", r["mech"].get("turn_count", 0))
                for r in results
            ),
            "multi_turn_cases": sum(1 for c in cases if len(usecases.case_turns(c)) > 1),
            "scenario_model": "driver_target",
            "evaluator_driver": "codex",
            "driver_scenario_closed_rate": (
                round(driver_closed_rate, 3) if driver_closed_rate is not None else None
            ),
            "efficiency_ux_weight_share": scoring.score_case(
                execution={"concluded": True, "stable": True, "driver_decision": {"scenario_closed": True}},
                check_result={"score": 1.0, "scope_ok": True},
                judge={"appropriate": 1.0, "coherent": 1.0, "conclusion_type": "completed"},
                responsiveness=1.0,
            )["efficiency_ux_weight_share"],
            "base_score": round(base_score, 2),
            "balanced_score": round(balanced_score, 2),
            "balance_factor_mean": round(balance_factor_mean, 3),
            "top_axis_scores": {
                k: round(100.0 * v, 1)
                for k, v in top_axis_means.items()
            },
            "axis_scores": {
                "task_fulfillment": round(100.0 * fulfillment_mean, 1),
                "evidence_truthfulness": round(100.0 * evidence_mean, 1),
                "outcome_reached": round(100.0 * outcome_mean, 1),
                "runtime_scope_safety": round(100.0 * runtime_scope_mean, 1),
                "responsiveness": round(100.0 * resp_mean, 1),
                "communication_quality": round(100.0 * communication_mean, 1),
                "closure": round(100.0 * outcome_mean, 1),
                "artifact_correctness": round(100.0 * evidence_mean, 1),
                "stability": round(100.0 * stable_rate, 1),
                "scope_discipline": round(100.0 * scope_mean, 1),
                "appropriateness": round(100.0 * fulfillment_mean, 1),
                "coherence": round(100.0 * communication_mean, 1),
            },
            "outcome_reached_mean": round(outcome_mean, 3),
            "mechanical_closure_rate": round(mechanical_closure_rate, 3),
            "closure_rate": round(outcome_mean, 3),
            "semantic_closure_rate": round(outcome_mean, 3),
            "stable_rate": round(stable_rate, 3),
            "responded_rate": round(responded_rate, 3),
            "task_fulfillment_mean": round(fulfillment_mean, 3),
            "evidence_truthfulness_mean": round(evidence_mean, 3),
            "artifact_correctness_mean": round(evidence_mean, 3),
            "runtime_scope_safety_mean": round(runtime_scope_mean, 3),
            "scope_discipline_mean": round(scope_mean, 3),
            "responsiveness_mean": round(resp_mean, 3),
            "communication_quality_mean": round(communication_mean, 3),
            "appropriate_mean": round(fulfillment_mean, 3),
            "coherent_mean": round(communication_mean, 3),
            "ttfa_p50_ms": _p50([r["mech"].get("ttfa_ms") for r in results]),
            "ttlt_p50_ms": _p50([r["mech"].get("ttlt_ms") for r in results]),
            "wall_p50_ms": _p50([r["mech"].get("wall_ms") for r in results]),
            "conclusion_types": ctypes,
            "judge_errors": sum(1 for r in results if r["judge"]["judge_error"]),
            "deterministic_checks": {
                "explicit": sum(r["checks"]["explicit_count"] for r in results),
                "failed": [
                    {"case": r["case"], "checks": [c for c in r["checks"]["checks"] if not c["ok"]]}
                    for r in results
                    if any(not c["ok"] for c in r["checks"]["checks"])
                ][:5],
            },
            "failures": failures,
            "side_effects": {
                "scope": "benchmark_workdir",
                "trials_with_files": len(side_effect_trials),
                "samples": side_effect_samples,
            },
            "case_results": [_redacted_case_result(r) for r in results],
        },
    }


def run_scenario(case_id: str) -> dict:
    """Run exactly one scenario id using the same primitive suites aggregate."""
    case = usecases.case_by_id(case_id)
    if not case:
        return {"skipped": True, "skip_reason": f"unknown scenario {case_id}"}
    return _run_cases([case], category=str(case["category"]))


def _run_category(category: str) -> dict:
    return _run_cases(usecases.cases_for(category), category=category)


def __getattr__(name: str):
    """Dynamically expose run_<category>() and run_case_<scenario>()."""
    case_prefix = "run_case_"
    if name.startswith(case_prefix):
        case_id = name[len(case_prefix):]
        if usecases.case_by_id(case_id):
            return lambda case_id=case_id: run_scenario(case_id)
    category_prefix = "run_"
    if name.startswith(category_prefix):
        category = name[len(category_prefix):]
        if category in usecases.categories():
            return lambda category=category: _run_category(category)
    raise AttributeError(name)
