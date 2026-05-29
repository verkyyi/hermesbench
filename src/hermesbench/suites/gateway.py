"""HermesBench gateway/runtime suites.

These suites measure Hermes runtime behavior that is not captured by the
single-turn ``chat -q`` use-case harness.
"""

from __future__ import annotations

import os


def run_gateway_ack_policy() -> dict:
    """Score deterministic gateway first-feedback policy.

    This wraps ``evals.responsiveness`` and does not call an LLM. It tests the
    configuration/runtime policy that decides whether long-running DM work gets
    an immediate acknowledgement while short/trivial/group turns do not.
    """
    try:
        from evals.responsiveness.run import run_benchmark
    except Exception as exc:
        return {
            "skipped": True,
            "skip_reason": f"Hermes Agent evals.responsiveness not importable: {type(exc).__name__}",
        }

    rep = run_benchmark()
    m = rep["metrics"]
    ack_accuracy = float(m.get("ack_accuracy") or 0.0)
    ack_recall = float(m.get("ack_recall") or 0.0)
    false_ack_score = 1.0 - float(m.get("false_ack_rate") or 0.0)
    cadence = float(m.get("cadence_ok_rate") or 0.0)
    p95 = float(m.get("long_work_p95_ttff_s") or 999.0)
    # Full credit at <=0.5s, zero at >=3s. This is policy-level simulated TTFF,
    # not live provider latency.
    responsiveness = max(0.0, min(1.0, 1.0 - max(0.0, p95 - 0.5) / 2.5))
    score = 100.0 * (
        0.35 * ack_accuracy
        + 0.20 * ack_recall
        + 0.15 * false_ack_score
        + 0.15 * cadence
        + 0.15 * responsiveness
    )
    return {
        "score": round(score, 2),
        "metrics": {
            "axis_scores": {
                "closure": 100.0,
                "stability": 100.0,
                "responsiveness": round(100.0 * responsiveness, 1),
                "appropriateness": round(100.0 * ack_accuracy, 1),
                "coherence": round(100.0 * cadence, 1),
            },
            "turns": m.get("turns_total"),
            "green_turns": m.get("green_turns"),
            "gap_turns": m.get("gap_turns"),
            "ack_accuracy": m.get("ack_accuracy"),
            "ack_recall": m.get("ack_recall"),
            "false_ack_rate": m.get("false_ack_rate"),
            "long_work_p95_ttff_s": m.get("long_work_p95_ttff_s"),
            "cadence_ok_rate": m.get("cadence_ok_rate"),
            "gap_turns_acked": m.get("gap_turns_acked"),
        },
    }


def run_origin_return() -> dict:
    """Optional real-LLM origin-return check.

    This wraps the standalone origin-return eval. It is intentionally opt-in
    because it spawns real agents and can take several minutes.
    """
    if not os.environ.get("HERMES_RUN_LLM_EVALS"):
        return {"skipped": True, "skip_reason": "HERMES_RUN_LLM_EVALS not set"}
    if os.environ.get("HERMES_BENCH_ORIGIN_RETURN") not in {"1", "true", "yes", "on"}:
        return {"skipped": True, "skip_reason": "HERMES_BENCH_ORIGIN_RETURN not set"}

    try:
        from evals.origin_return import run as origin
    except Exception as exc:
        return {
            "skipped": True,
            "skip_reason": f"Hermes Agent evals.origin_return not importable: {type(exc).__name__}",
        }

    origin._isolate_board()
    ok_a, msg_a, task_id = origin.phase_a()
    ok_b, msg_b = (False, "phase a did not produce a task")
    if task_id:
        ok_b, msg_b = origin.phase_b(task_id)
    phase_scores = [1.0 if ok_a else 0.0, 1.0 if ok_b else 0.0]
    score = 100.0 * sum(phase_scores) / len(phase_scores)
    return {
        "score": round(score, 2),
        "metrics": {
            "axis_scores": {
                "closure": round(100.0 * (1.0 if ok_b else 0.0), 1),
                "stability": 100.0,
                "responsiveness": 100.0,
                "appropriateness": round(100.0 * sum(phase_scores) / len(phase_scores), 1),
                "coherence": 100.0,
            },
            "phase_a": {"ok": ok_a, "message": msg_a},
            "phase_b": {"ok": ok_b, "message": msg_b},
        },
    }
