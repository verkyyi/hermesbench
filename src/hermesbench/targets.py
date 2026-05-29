"""Target adapters.

Target adapters are the only layer that knows how to talk to a concrete agent
framework. Cases and drivers stay target-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

from hermesbench import harness


@dataclass
class HermesCliTarget:
    """Target adapter for Hermes `chat -q` in an isolated benchmark session."""

    def run_turns(self, turns: list[dict], *, timeout_s: int) -> dict:
        if len(turns) == 1:
            result = harness.run_case(turns[0]["prompt"], timeout_s=timeout_s)
            result["turns"] = [dict(result, turn_index=1, profile="default")]
            result["transcript"] = [
                {"turn": 1, "user": turns[0]["prompt"], "assistant": result.get("reply", "")}
            ]
            result["turn_count"] = 1
            result["expected_turn_count"] = 1
            result["scenario_completion_rate"] = 1.0
            return result
        return harness.run_scenario(turns, timeout_s=timeout_s)


def build_target() -> HermesCliTarget:
    """Build the target adapter for this run.

    The first public implementation targets Hermes. Other target frameworks can
    plug in here without changing cases.
    """
    return HermesCliTarget()
