"""Suite registry for HermesBench (v2 — harness-driven, reliability-first).

Each suite is one use-case *category*. Its `run()` drives Hermes through a
harness (single-turn, multi-turn, or runtime/multi-profile), judges the
observable result, and returns a normalized
``{score: 0..100, metrics: {...}}`` (or ``{skipped: True, skip_reason}``).
Prompt suites evaluate from the user's perspective and runtime suites may add
auditable internal/runtime checks for behavior that is otherwise invisible, such
as kanban origin-return preservation. All suites weight
reliability/responsiveness/closure above capability.

Most suites drive real agents, so model-backed suites self-skip when
HERMES_RUN_LLM_EVALS is unset. Deterministic runtime-policy suites can still
run without model credentials.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable

from hermesbench import usecases

# Grading modes, mirroring ClawBench Core v1. Every v2 suite is ``hybrid``:
# mechanical reliability signals (responded / latency / stable / concluded) plus
# an LLM judge for conclusion-type, appropriateness, and coherence.
AUTOMATED = "automated"
LLM_JUDGE = "llm_judge"
HYBRID = "hybrid"

SINGLE_TURN = "single_turn"
MULTI_TURN = "multi_turn"
RUNTIME_POLICY = "runtime_policy"
MULTI_PROFILE = "multi_profile"


@dataclass(frozen=True)
class Suite:
    id: str
    category: str
    mode: str
    weight: float
    runner: str  # "module:function" — imported lazily at execution time
    summary: str = ""
    interaction: str = SINGLE_TURN

    def load(self) -> Callable[[], dict]:
        mod_name, _, fn_name = self.runner.partition(":")
        mod = importlib.import_module(mod_name)
        return getattr(mod, fn_name)


_RUNNER = "hermesbench.suites.usecases:run_{}"


def _prompt_suites() -> list[Suite]:
    # One suite per use-case category. Equal weight — the
    # reliability-over-capability bias lives inside each suite's score formula,
    # not in the cross-category weights. Built dynamically so local suite files
    # supplied via HERMESBENCH_SUITE_PATH are picked up without custom code.
    suites: list[Suite] = []
    for cat in usecases.categories():
        label = usecases.category_label(cat)
        package = usecases.package_for(cat) or "unknown"
        suites.append(Suite(
            id=cat,
            category=label,
            mode=HYBRID,
            weight=1.0,
            runner=_RUNNER.format(cat),
            summary=f"Black-box {label} use cases ({package}) — "
                    "closure, stability, responsiveness, appropriateness.",
            interaction=MULTI_TURN,
        ))
    return suites


def _runtime_suites() -> list[Suite]:
    return [
        Suite(
            id="gateway_ack_policy",
            category="Gateway ack policy",
            mode=AUTOMATED,
            weight=1.0,
            runner="hermesbench.suites.gateway:run_gateway_ack_policy",
            summary="Gateway pre-LLM acknowledgement policy and progress cadence.",
            interaction=RUNTIME_POLICY,
        ),
        Suite(
            id="origin_return",
            category="Async origin return",
            mode=HYBRID,
            weight=1.0,
            runner="hermesbench.suites.gateway:run_origin_return",
            summary="Optional kanban/multi-profile check that delegated work preserves user return path.",
            interaction=MULTI_PROFILE,
        ),
    ]


def all_suites() -> list[Suite]:
    return [*_prompt_suites(), *_runtime_suites()]


def by_id(suite_id: str) -> Suite | None:
    return next((s for s in all_suites() if s.id == suite_id), None)


def select(*, ids: list[str] | None = None) -> list[Suite]:
    """Select suites for a run, optionally restricted to named ``ids``."""
    if not ids:
        return all_suites()
    wanted = set(ids)
    return [s for s in all_suites() if s.id in wanted]
