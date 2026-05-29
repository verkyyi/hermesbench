"""Driver adapters.

Drivers orchestrate scenarios against a target adapter. They may be static,
deterministic state machines, or later bounded agent controllers. Drivers do
not solve the task for the target; they provide user turns and observations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StaticDriver:
    """Replay the scenario's declared turns exactly."""

    def run(self, scenario: dict, target, *, timeout_s: int) -> dict:
        turns = list(scenario.get("turns") or [{"prompt": scenario["initial_prompt"]}])
        max_turns = int((scenario.get("driver") or {}).get("max_turns") or len(turns))
        turns = turns[:max(1, max_turns)]
        result = target.run_turns(turns, timeout_s=timeout_s)
        result["driver"] = {
            "kind": "static",
            "max_turns": max_turns,
            "turns_sent": len(turns),
        }
        return result


def build_driver(scenario: dict):
    kind = str((scenario.get("driver") or {}).get("kind") or "static")
    if kind != "static":
        raise ValueError(f"unsupported driver kind: {kind}")
    return StaticDriver()


def run(scenario: dict, target, *, timeout_s: int) -> dict:
    """Run one scenario using its configured driver."""
    return build_driver(scenario).run(scenario, target, timeout_s=timeout_s)
