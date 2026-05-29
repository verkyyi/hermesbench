"""HermesBench gateway/runtime suites.

These suites measure Hermes runtime behavior that is not captured by the
single-turn ``chat -q`` use-case harness.
"""

from __future__ import annotations

import os


_TRUE = {"1", "true", "yes", "on"}


def _requested_worker_profiles() -> list[str]:
    raw = os.environ.get("HERMES_BENCH_WORKER_PROFILES", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _profile_inventory() -> dict:
    try:
        from hermes_cli.profiles import list_profiles, profile_exists  # type: ignore
    except Exception as exc:
        requested = _requested_worker_profiles()
        return {
            "available": [],
            "requested": requested,
            "missing_requested": requested,
            "inventory_error": f"{type(exc).__name__}: {exc}"[:200],
        }

    try:
        infos = list_profiles()
        available = sorted(str(getattr(info, "name", "") or "") for info in infos if getattr(info, "name", None))
    except Exception as exc:
        available = []
        inventory_error = f"{type(exc).__name__}: {exc}"[:200]
    else:
        inventory_error = None

    requested = _requested_worker_profiles()
    missing = []
    for name in requested:
        try:
            if not profile_exists(name):
                missing.append(name)
        except Exception:
            missing.append(name)
    out = {"available": available, "requested": requested, "missing_requested": missing}
    if inventory_error:
        out["inventory_error"] = inventory_error
    return out


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
            "top_axis_scores": {
                "capability_truthfulness": round(100.0 * ((ack_accuracy + false_ack_score) / 2.0), 1),
                "reliability_safety": 100.0,
                "efficiency_ux": round(100.0 * ((responsiveness + cadence) / 2.0), 1),
            },
            "axis_scores": {
                "task_fulfillment": round(100.0 * ack_accuracy, 1),
                "evidence_truthfulness": round(100.0 * false_ack_score, 1),
                "outcome_reached": 100.0,
                "runtime_scope_safety": 100.0,
                "communication_quality": round(100.0 * cadence, 1),
                "closure": 100.0,
                "artifact_correctness": round(100.0 * false_ack_score, 1),
                "stability": 100.0,
                "scope_discipline": 100.0,
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


def _delegated_closure_enabled() -> bool:
    return (
        os.environ.get("HERMES_BENCH_DELEGATED_CLOSURE") in _TRUE
        or os.environ.get("HERMES_BENCH_ORIGIN_RETURN") in _TRUE
    )


def run_delegated_closure() -> dict:
    """Optional real-LLM kanban delegated-closure check.

    This wraps the standalone Hermes Agent origin-return eval. The public suite
    name is delegated_closure because the user-facing contract is easier to
    understand: delegated work should still reach closure for the user. It is
    intentionally opt-in because it spawns real agents and can take several
    minutes. For multi-profile configurations, set
    HERMES_BENCH_WORKER_PROFILES=orchestrator,worker-code,... so the run records
    which profiles are part of the published baseline contract.
    """
    if not os.environ.get("HERMES_RUN_LLM_EVALS"):
        return {"skipped": True, "skip_reason": "HERMES_RUN_LLM_EVALS not set"}
    if not _delegated_closure_enabled():
        return {"skipped": True, "skip_reason": "HERMES_BENCH_DELEGATED_CLOSURE not set"}

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
    inventory = _profile_inventory()
    missing = inventory.get("missing_requested") or []
    profile_score = 1.0 if not missing else 0.0
    # Preserve the original e2e behavior as the main score, but fold required
    # profile disclosure into the same score-only verdict.
    score = 100.0 * (
        0.35 * (1.0 if ok_a else 0.0)
        + 0.45 * (1.0 if ok_b else 0.0)
        + 0.20 * profile_score
    )
    return {
        "score": round(score, 2),
        "metrics": {
            "top_axis_scores": {
                "capability_truthfulness": round(100.0 * ((1.0 if ok_a else 0.0) + (1.0 if ok_b else 0.0)) / 2.0, 1),
                "reliability_safety": round(100.0 * ((1.0 if ok_b else 0.0) + profile_score) / 2.0, 1),
                "efficiency_ux": 100.0,
            },
            "axis_scores": {
                "task_fulfillment": round(100.0 * ((1.0 if ok_a else 0.0) + (1.0 if ok_b else 0.0)) / 2.0, 1),
                "evidence_truthfulness": round(100.0 * profile_score, 1),
                "outcome_reached": round(100.0 * (1.0 if ok_b else 0.0), 1),
                "runtime_scope_safety": round(100.0 * profile_score, 1),
                "communication_quality": 100.0,
                "closure": round(100.0 * (1.0 if ok_b else 0.0), 1),
                "artifact_correctness": round(100.0 * profile_score, 1),
                "stability": round(100.0 * profile_score, 1),
                "scope_discipline": 100.0,
                "responsiveness": 100.0,
                "appropriateness": round(100.0 * ((1.0 if ok_a else 0.0) + (1.0 if ok_b else 0.0)) / 2.0, 1),
                "coherence": 100.0,
            },
            "interaction": "multi_profile",
            "phase_a": {"ok": ok_a, "message": msg_a},
            "phase_b": {"ok": ok_b, "message": msg_b},
            "profile_coverage": inventory,
        },
    }


def run_origin_return() -> dict:
    """Backward-compatible alias for the old suite name."""
    return run_delegated_closure()
