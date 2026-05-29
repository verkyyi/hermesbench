"""HermesBench suite adapters.

Each module exposes ``run() -> dict`` returning normalized fields:
    {"score": 0..100, "metrics": dict}
or, when a suite cannot run in the current environment:
    {"skipped": True, "skip_reason": str}

Heavy imports (agent runtime, kanban kernel) are done *inside* run() so that a
core-only run never pays for them.
"""
