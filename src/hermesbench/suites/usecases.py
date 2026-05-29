"""HermesBench v2 use-case suites — one per category.

For each case in a category we drive the default profile in an isolated turn
(harness), then judge the reply (judge). The category score weights reliability
far above capability:

    score = 100 · (0.40·closure + 0.20·stable + 0.15·responsiveness + 0.25·appropriate)

The final score is the only verdict. Closure, stability, and appropriateness
are folded into the score as multiplicative penalties, so a correct-looking but
non-concluding turn cannot hide behind a high average.

All suites self-skip without HERMES_RUN_LLM_EVALS (they drive real agents).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from hermesbench import harness, usecases
from hermesbench import judge as judge_mod

TRIALS = int(os.environ.get("HERMES_BENCH_TRIALS", "2"))
CONCURRENCY = int(os.environ.get("HERMES_BENCH_CONCURRENCY", "4"))
APPROPRIATENESS_TARGET = float(
    os.environ.get(
        "HERMES_BENCH_APPROPRIATENESS_TARGET",
        os.environ.get("HERMES_BENCH_APPROPRIATE_PASS", "0.7"),
    )
)


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


def _score(
    *,
    closure_rate: float,
    stable_rate: float,
    responsiveness_mean: float,
    appropriate_mean: float,
) -> tuple[float, float]:
    """Return final score and pre-penalty base score.

    The base score preserves the axis weighting. The final score then applies
    score-only gates: incomplete closure/stability and below-target
    appropriateness reduce the score instead of producing a separate pass/fail.
    """
    base = 100.0 * (
        0.40 * closure_rate
        + 0.20 * stable_rate
        + 0.15 * responsiveness_mean
        + 0.25 * appropriate_mean
    )
    reliability_factor = max(0.0, min(1.0, closure_rate * stable_rate))
    if APPROPRIATENESS_TARGET <= 0:
        appropriateness_factor = 1.0
    else:
        appropriateness_factor = max(0.0, min(1.0, appropriate_mean / APPROPRIATENESS_TARGET))
    return base * reliability_factor * appropriateness_factor, base


def _run_trial(case: dict, b: dict) -> dict:
    m = harness.run_case(case["prompt"], timeout_s=int(b["conclude_s"]) + 30)
    v = judge_mod.judge(case, m["reply"])
    genuine = bool(m["concluded"]) and v["conclusion_type"] != "none"
    return {
        "case": case["id"],
        "expectation": case.get("expectation"),
        "mech": m,
        "judge": v,
        "genuine_conclusion": genuine,
        "responsiveness": _responsiveness(m.get("ttfa_ms"), m.get("wall_ms"), b["reply_target_s"]),
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
    closure_rate = sum(1 for r in results if r["genuine_conclusion"]) / n
    stable_rate = sum(1 for r in results if r["mech"]["stable"]) / n
    responded_rate = sum(1 for r in results if r["mech"]["responded"]) / n
    resp_mean = sum(r["responsiveness"] for r in results) / n

    judged = [r for r in results if not r["judge"]["judge_error"]]
    appropriate_mean = (sum(r["judge"]["appropriate"] for r in judged) / len(judged)) if judged else 0.0
    coherent_mean = (sum(r["judge"]["coherent"] for r in judged) / len(judged)) if judged else 0.0

    score, base_score = _score(
        closure_rate=closure_rate,
        stable_rate=stable_rate,
        responsiveness_mean=resp_mean,
        appropriate_mean=appropriate_mean,
    )

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
            "base_score": round(base_score, 2),
            "axis_scores": {
                "closure": round(100.0 * closure_rate, 1),
                "stability": round(100.0 * stable_rate, 1),
                "responsiveness": round(100.0 * resp_mean, 1),
                "appropriateness": round(100.0 * appropriate_mean, 1),
                "coherence": round(100.0 * coherent_mean, 1),
            },
            "closure_rate": round(closure_rate, 3),
            "stable_rate": round(stable_rate, 3),
            "responded_rate": round(responded_rate, 3),
            "responsiveness_mean": round(resp_mean, 3),
            "appropriate_mean": round(appropriate_mean, 3),
            "coherent_mean": round(coherent_mean, 3),
            "ttfa_p50_ms": _p50([r["mech"].get("ttfa_ms") for r in results]),
            "ttlt_p50_ms": _p50([r["mech"].get("ttlt_ms") for r in results]),
            "wall_p50_ms": _p50([r["mech"].get("wall_ms") for r in results]),
            "conclusion_types": ctypes,
            "judge_errors": sum(1 for r in results if r["judge"]["judge_error"]),
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
