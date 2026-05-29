"""HermesBench v2 use-case suites — one per category.

For each case in a category, a driver orchestrates a target adapter against a
driver/target-agnostic scenario. The first bundled driver is static replay of
the declared prompt/turns; target selection is run configuration. Scoring is
deterministic-first: mechanical signals, artifact checks, scope checks, and
latency dominate; LLM judgement is used only for semantic appropriateness and
coherence.

The final score is the only verdict. Closure, stability, scope, deterministic
checks, and judged semantics are folded into the score, so a correct-looking but
non-concluding or artifact-wrong turn cannot hide behind a high average.

All suites self-skip without HERMES_RUN_LLM_EVALS (they drive real agents).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from hermesbench import checks, drivers, scenarios, scoring, targets, usecases
from hermesbench import judge as judge_mod

TRIALS = int(os.environ.get("HERMES_BENCH_TRIALS", "2"))
CONCURRENCY = int(os.environ.get("HERMES_BENCH_CONCURRENCY", "4"))


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
            "driver": (m.get("driver") or {}).get("kind", "static"),
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


def _run_category(category: str) -> dict:
    if not os.environ.get("HERMES_RUN_LLM_EVALS"):
        return {"skipped": True, "skip_reason": "HERMES_RUN_LLM_EVALS not set"}

    cases = usecases.cases_for(category)
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
    closure_rate = sum(1 for r in results if r["mech"]["concluded"]) / n
    semantic_closure_rate = sum(1 for r in results if r["genuine_conclusion"]) / n
    stable_rate = sum(1 for r in results if r["mech"]["stable"]) / n
    responded_rate = sum(1 for r in results if r["mech"]["responded"]) / n
    driver_decisions = [r["driver_decision"] for r in results if r["driver_decision"]]
    driver_closed_rate = (
        sum(1 for d in driver_decisions if d.get("scenario_closed")) / len(driver_decisions)
        if driver_decisions else None
    )
    resp_mean = sum(r["responsiveness"] for r in results) / n
    artifact_mean = sum(r["score"]["axes"]["artifact_correctness"] for r in results) / n
    scope_mean = sum(r["score"]["axes"]["scope_discipline"] for r in results) / n

    judged = [r for r in results if not r["judge"]["judge_error"]]
    appropriate_mean = (sum(r["judge"]["appropriate"] for r in judged) / len(judged)) if judged else 0.0
    coherent_mean = (sum(r["judge"]["coherent"] for r in judged) / len(judged)) if judged else 0.0
    score = sum(r["score"]["score"] for r in results) / n
    base_score = sum(r["score"]["base_score"] for r in results) / n

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
            "driver_kinds": sorted({r["scenario"]["driver"] for r in results}),
            "driver_scenario_closed_rate": (
                round(driver_closed_rate, 3) if driver_closed_rate is not None else None
            ),
            "deterministic_weight_share": scoring.score_case(
                execution={"concluded": True, "stable": True},
                check_result={"score": 1.0, "scope_ok": True},
                judge={"appropriate": 1.0, "coherent": 1.0, "conclusion_type": "completed"},
                responsiveness=1.0,
            )["deterministic_weight_share"],
            "base_score": round(base_score, 2),
            "axis_scores": {
                "closure": round(100.0 * closure_rate, 1),
                "artifact_correctness": round(100.0 * artifact_mean, 1),
                "stability": round(100.0 * stable_rate, 1),
                "scope_discipline": round(100.0 * scope_mean, 1),
                "responsiveness": round(100.0 * resp_mean, 1),
                "appropriateness": round(100.0 * appropriate_mean, 1),
                "coherence": round(100.0 * coherent_mean, 1),
            },
            "closure_rate": round(closure_rate, 3),
            "semantic_closure_rate": round(semantic_closure_rate, 3),
            "stable_rate": round(stable_rate, 3),
            "responded_rate": round(responded_rate, 3),
            "artifact_correctness_mean": round(artifact_mean, 3),
            "scope_discipline_mean": round(scope_mean, 3),
            "responsiveness_mean": round(resp_mean, 3),
            "appropriate_mean": round(appropriate_mean, 3),
            "coherent_mean": round(coherent_mean, 3),
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
        },
    }


def __getattr__(name: str):
    """Dynamically expose run_<category>() for every dataset category."""
    prefix = "run_"
    if name.startswith(prefix):
        category = name[len(prefix):]
        if category in usecases.categories():
            return lambda category=category: _run_category(category)
    raise AttributeError(name)
