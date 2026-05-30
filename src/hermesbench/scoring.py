"""Evidence-grounded case scoring."""

from __future__ import annotations


CAPABILITY_WEIGHTS = {
    "task_fulfillment": 0.45,
    "evidence_truthfulness": 0.35,
    "artifact_correctness": 0.20,
}

RELIABILITY_WEIGHTS = {
    "outcome_reached": 0.40,
    "stability": 0.25,
    "scope_discipline": 0.20,
    "responsiveness": 0.15,
}

TOP_AXIS_WEIGHTS = {
    "capability_truthfulness": 0.70,
    "reliability_safety": 0.20,
    "efficiency_ux": 0.10,
}

# Compatibility view of the final weighted score by stored axis name.
AXIS_WEIGHTS = {
    "task_fulfillment": TOP_AXIS_WEIGHTS["capability_truthfulness"] * CAPABILITY_WEIGHTS["task_fulfillment"],
    "evidence_truthfulness": TOP_AXIS_WEIGHTS["capability_truthfulness"] * CAPABILITY_WEIGHTS["evidence_truthfulness"],
    "artifact_correctness": TOP_AXIS_WEIGHTS["capability_truthfulness"] * CAPABILITY_WEIGHTS["artifact_correctness"],
    "outcome_reached": TOP_AXIS_WEIGHTS["reliability_safety"] * RELIABILITY_WEIGHTS["outcome_reached"],
    "stability": TOP_AXIS_WEIGHTS["reliability_safety"] * RELIABILITY_WEIGHTS["stability"],
    "scope_discipline": TOP_AXIS_WEIGHTS["reliability_safety"] * RELIABILITY_WEIGHTS["scope_discipline"],
    "responsiveness": TOP_AXIS_WEIGHTS["reliability_safety"] * RELIABILITY_WEIGHTS["responsiveness"],
    "communication_quality": TOP_AXIS_WEIGHTS["efficiency_ux"],
}


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _outcome_reached(execution: dict, judge: dict) -> float:
    """A reply only counts as an outcome when the judge sees a real terminal state."""
    if not _has_assistant_reply(execution):
        return 0.0
    driver_decision = execution.get("driver_decision")
    if isinstance(driver_decision, dict) and driver_decision.get("scenario_closed") is False:
        return 0.0
    if judge.get("conclusion_type") == "none":
        return 0.0
    if execution.get("concluded"):
        return 1.0
    if isinstance(driver_decision, dict) and driver_decision.get("scenario_closed") is True:
        return 1.0
    return 0.0


def _has_assistant_reply(execution: dict) -> bool:
    if str(execution.get("reply") or "").strip():
        return True
    for item in execution.get("transcript") or []:
        if isinstance(item, dict) and str(item.get("assistant") or "").strip():
            return True
    return False


def _returncode_failed(execution: dict) -> bool:
    rc = execution.get("returncode")
    return rc is not None and rc != 0


def score_case(*, execution: dict, check_result: dict, judge: dict, responsiveness: float) -> dict:
    """Score a case from deterministic evidence and bounded judge evidence."""
    outcome = _outcome_reached(execution, judge)
    stability = 1.0 if execution.get("stable") else 0.0
    scope = 1.0 if check_result.get("scope_ok") else 0.0
    artifact = check_result.get("score") if check_result.get("score") is not None else 1.0
    artifact_score = _clamp01(artifact)
    fulfillment = _clamp01(judge.get("appropriate"))
    evidence = min(artifact_score, fulfillment)
    runtime_scope = min(stability, scope)
    communication = _clamp01(judge.get("coherent"))

    axes = {
        "outcome_reached": outcome,
        "task_fulfillment": fulfillment,
        "evidence_truthfulness": evidence,
        "runtime_scope_safety": runtime_scope,
        "responsiveness": _clamp01(responsiveness),
        "communication_quality": communication,
    }
    # Backward-compatible alias for stored artifacts and existing dashboards.
    axes["closure"] = axes["outcome_reached"]
    axes["artifact_correctness"] = artifact_score
    axes["stability"] = stability
    axes["scope_discipline"] = scope
    axes["appropriateness"] = axes["task_fulfillment"]
    axes["coherence"] = axes["communication_quality"]

    capability = sum(CAPABILITY_WEIGHTS[k] * axes[k] for k in CAPABILITY_WEIGHTS)
    reliability = sum(RELIABILITY_WEIGHTS[k] * axes[k] for k in RELIABILITY_WEIGHTS)
    top_axes = {
        "capability_truthfulness": capability,
        "reliability_safety": reliability,
        "efficiency_ux": communication,
    }

    base = 100.0 * sum(TOP_AXIS_WEIGHTS[k] * top_axes[k] for k in TOP_AXIS_WEIGHTS)
    balanced = base
    cap_reasons: list[str] = []
    cap = 100.0
    hard_zero = False
    if not _has_assistant_reply(execution):
        cap = 0.0
        hard_zero = True
        cap_reasons.append("no_assistant_reply")
    elif outcome <= 0.0:
        cap = min(cap, 30.0)
        cap_reasons.append("no_terminal_outcome")
    if scope <= 0.0:
        cap = min(cap, 20.0)
        cap_reasons.append("scope_violation")
    if not hard_zero and (bool(execution.get("timed_out")) or _returncode_failed(execution)):
        cap = min(cap, 50.0)
        cap_reasons.append("crash_or_timeout")
    if not hard_zero and stability <= 0.0:
        cap = min(cap, 75.0)
        cap_reasons.append("runtime_unstable")
    if int(check_result.get("explicit_count") or 0) > 0 and artifact_score < 1.0:
        cap = min(cap, 60.0)
        cap_reasons.append("explicit_check_failed")
    final = min(base, cap)
    return {
        "score": final,
        "base_score": base,
        "balanced_score": balanced,
        "capability_score": 100.0 * capability,
        "reliability_score": 100.0 * reliability,
        "communication_score": 100.0 * communication,
        "axes": axes,
        "top_axes": top_axes,
        "balance_factor": 1.0,
        "outcome_gate": outcome,
        "runtime_scope_gate": runtime_scope,
        "stability_gate": stability,
        "scope_gate": scope,
        "score_cap": cap,
        "score_cap_reasons": cap_reasons,
        "efficiency_ux_weight_share": TOP_AXIS_WEIGHTS["efficiency_ux"],
        "scoring_policy": "capability_weighted_with_reliability_caps_v1",
    }
