"""HermesBench — harness-driven reliability benchmark for Hermes Agent.

Runs driver/target-agnostic scenarios against a target agent adapter, judges
replies/transcripts with an LLM only where semantics are needed, and scores
evidence-backed outcomes across three top axes: capability/truthfulness,
reliability/safety, and efficiency/UX. Prompt suites stay black-box; explicit
runtime suites can evaluate auditable kanban/multi-profile contracts. Persists
runs to a SQLite trend store and can emit JSON for dashboards or public
reporting.

Design notes:
  - Cases define goals/prompts/fixtures/checks; run config chooses driver/target.
  - Reliability > capability; **every prompt must reach a genuine outcome**
    (answer / refusal / clarification) — outcome reached is the headline
    contract.
  - Evidence-grounded hybrid grading: mechanical reliability + artifact/scope
    checks bound LLM judge rulings on outcome, fulfillment, and communication.
  - Harness pinned: each run records git sha, model id, profile hash, profile
    snapshot, and scoped side-effect artifact manifests (the "harness effect" —
    same weights swing 10-50pts across harnesses).
  - Local JSON/YAML suites can be loaded without writing custom runner, store,
    report, or dashboard code.

Entry point:
    HERMES_RUN_LLM_EVALS=1 venv/bin/python -m hermesbench.run   # default single recipe
    venv/bin/python -m hermesbench.run --suite general_assistant,mail_assistant
    venv/bin/python -m hermesbench.run --full-bundle
    venv/bin/python -m hermesbench.run --json

Coding-agent API:
    from hermesbench.api import run_scenario, list_scenarios, validate
    report = run_scenario("calendar_daily_brief", persist=False)
"""

__version__ = "0.1.0"
