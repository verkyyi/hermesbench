"""Scenario normalization for driver-target HermesBench cases.

Cases stay driver- and target-agnostic: they describe the user goal, initial
prompt/turns, optional fixtures, deterministic checks, and scoring intent. Run
configuration chooses the driver and target adapters.
"""

from __future__ import annotations

import os

from hermesbench import usecases


def from_case(case: dict) -> dict:
    """Return a normalized scenario spec for a use-case dict."""
    turns = usecases.case_turns(case)
    initial_prompt = str(case.get("initial_prompt") or case.get("prompt") or turns[0]["prompt"])
    raw_driver = dict(case.get("driver") or {})
    driver = dict(raw_driver)
    driver.setdefault("kind", os.environ.get("HERMES_BENCH_DRIVER") or "codex")
    driver["_declared_max_turns"] = "max_turns" in raw_driver
    if "max_turns" not in driver:
        driver["max_turns"] = len(turns)

    return {
        "id": str(case["id"]),
        "category": str(case.get("category") or ""),
        "audience": usecases.package_for(str(case.get("category") or "")),
        "goal": str(case.get("goal") or case.get("notes") or initial_prompt),
        "initial_prompt": initial_prompt,
        "turns": turns,
        "expectation": case.get("expectation", "answer"),
        "notes": case.get("notes") or "",
        "fixture": case.get("fixture"),
        "driver": driver,
        "checks": list(case.get("checks") or []),
        "scoring": dict(case.get("scoring") or {}),
    }


def prompt_for_judge(scenario: dict) -> str:
    """Human-readable user side of a scenario for judge prompts."""
    turns = scenario.get("turns") or [{"prompt": scenario.get("initial_prompt", "")}]
    if len(turns) == 1:
        return str(turns[0]["prompt"])
    return "\n\n".join(
        f"Turn {idx}: {turn['prompt']}" for idx, turn in enumerate(turns, start=1)
    )
