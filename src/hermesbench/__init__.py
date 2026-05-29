"""HermesBench — harness-driven reliability benchmark for Hermes Agent.

Drives Hermes as an end user would (isolated `hermes chat -q` scenarios),
judges replies/transcripts with an LLM, and scores reliability/responsiveness/
closure above capability. Prompt suites stay black-box; explicit runtime suites
can evaluate auditable kanban/multi-profile contracts. Persists runs to a SQLite
trend store and can emit JSON for dashboards or public reporting.

Design notes:
  - Harness-driven single-turn and multi-turn scenarios.
  - Reliability > capability; **every prompt must reach a genuine conclusion**
    (answer / refusal / clarification) — closure is the headline contract.
  - Hybrid grading: mechanical reliability signals (responded / latency /
    stable / concluded) + an LLM judge (conclusion-type / appropriate /
    coherent). No pass/fail tier concept; all prompt suites drive real agents
    and self-skip without HERMES_RUN_LLM_EVALS.
  - Harness pinned: each run records git sha, model id, profile hash, profile
    snapshot, and scoped side-effect artifact manifests (the "harness effect" —
    same weights swing 10-50pts across harnesses).
  - Local JSON/YAML suites can be loaded without writing custom runner, store,
    report, or dashboard code.

Entry point:
    HERMES_RUN_LLM_EVALS=1 venv/bin/python -m hermesbench.run   # all use cases
    venv/bin/python -m hermesbench.run --suite runtime_config,ambiguous_followup
    venv/bin/python -m hermesbench.run --json
"""

__version__ = "0.1.0"
