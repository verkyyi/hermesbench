"""Deterministic-first case scoring."""

from __future__ import annotations


AXIS_WEIGHTS = {
    "closure": 0.25,
    "artifact_correctness": 0.20,
    "stability": 0.15,
    "scope_discipline": 0.15,
    "responsiveness": 0.10,
    "appropriateness": 0.10,
    "coherence": 0.05,
}


def score_case(*, execution: dict, check_result: dict, judge: dict, responsiveness: float) -> dict:
    """Score a case from deterministic evidence first, judge evidence second."""
    closure = 1.0 if execution.get("concluded") else 0.0
    stability = 1.0 if execution.get("stable") else 0.0
    scope = 1.0 if check_result.get("scope_ok") else 0.0
    artifact = float(check_result.get("score") if check_result.get("score") is not None else 1.0)
    appropriate = float(judge.get("appropriate") or 0.0)
    coherent = float(judge.get("coherent") or 0.0)

    axes = {
        "closure": closure,
        "artifact_correctness": max(0.0, min(1.0, artifact)),
        "stability": stability,
        "scope_discipline": scope,
        "responsiveness": max(0.0, min(1.0, responsiveness)),
        "appropriateness": max(0.0, min(1.0, appropriate)),
        "coherence": max(0.0, min(1.0, coherent)),
    }
    base = 100.0 * sum(AXIS_WEIGHTS[k] * axes[k] for k in AXIS_WEIGHTS)

    deterministic_gate = closure * stability * scope
    semantic_gate = 0.0 if judge.get("conclusion_type") == "none" else 1.0
    final = base * deterministic_gate * semantic_gate
    deterministic_weight = sum(AXIS_WEIGHTS[k] for k in (
        "closure", "artifact_correctness", "stability", "scope_discipline", "responsiveness"
    ))
    return {
        "score": final,
        "base_score": base,
        "axes": axes,
        "deterministic_gate": deterministic_gate,
        "semantic_gate": semantic_gate,
        "deterministic_weight_share": deterministic_weight,
    }
