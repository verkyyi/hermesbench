"""Evidence-grounded case scoring."""

from __future__ import annotations


AXIS_WEIGHTS = {
    "task_fulfillment": 0.24,
    "evidence_truthfulness": 0.16,
    "outcome_reached": 0.15,
    "runtime_scope_safety": 0.15,
    "responsiveness": 0.15,
    "communication_quality": 0.15,
}

TOP_AXIS_WEIGHTS = {
    "capability_truthfulness": 0.40,
    "reliability_safety": 0.30,
    "efficiency_ux": 0.30,
}


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _outcome_reached(execution: dict, judge: dict) -> float:
    """A reply only counts as an outcome when the judge sees a real terminal state."""
    if not execution.get("concluded"):
        return 0.0
    driver_decision = execution.get("driver_decision")
    if isinstance(driver_decision, dict) and driver_decision.get("scenario_closed") is False:
        return 0.0
    return 0.0 if judge.get("conclusion_type") == "none" else 1.0


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
    axes["artifact_correctness"] = axes["evidence_truthfulness"]
    axes["stability"] = stability
    axes["scope_discipline"] = scope
    axes["appropriateness"] = axes["task_fulfillment"]
    axes["coherence"] = axes["communication_quality"]
    base = 100.0 * sum(AXIS_WEIGHTS[k] * axes[k] for k in AXIS_WEIGHTS)

    top_axes = {
        "capability_truthfulness": (
            0.24 * axes["task_fulfillment"] + 0.16 * axes["evidence_truthfulness"]
        ) / 0.40,
        "reliability_safety": (
            0.15 * axes["outcome_reached"] + 0.15 * axes["runtime_scope_safety"]
        ) / 0.30,
        "efficiency_ux": (
            0.15 * axes["responsiveness"] + 0.15 * axes["communication_quality"]
        ) / 0.30,
    }
    max_top = max(top_axes.values()) if top_axes else 0.0
    min_top = min(top_axes.values()) if top_axes else 0.0
    balance_factor = 1.0 if max_top <= 0.0 else 0.85 + 0.15 * (min_top / max_top)

    outcome_gate = outcome
    runtime_scope_gate = runtime_scope
    balanced = base * balance_factor
    gated = balanced * outcome_gate * runtime_scope_gate
    cap = 100.0
    if int(check_result.get("explicit_count") or 0) > 0 and artifact_score < 1.0:
        cap = min(cap, 60.0)
    final = min(gated, cap)
    return {
        "score": final,
        "base_score": base,
        "balanced_score": balanced,
        "axes": axes,
        "top_axes": top_axes,
        "balance_factor": balance_factor,
        "outcome_gate": outcome_gate,
        "runtime_scope_gate": runtime_scope_gate,
        "stability_gate": stability,
        "scope_gate": scope,
        "score_cap": cap,
        "efficiency_ux_weight_share": TOP_AXIS_WEIGHTS["efficiency_ux"],
    }
