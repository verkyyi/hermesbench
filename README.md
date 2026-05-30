# HermesBench

HermesBench is a reliability-first benchmark and reusable evaluation harness for
**Hermes Agent runtime configurations**.

It is not a model leaderboard. The unit under test is the whole Hermes setup:
profile prompt, model/provider choice, tools, skills, memory, gateway behavior,
delegation/routing, safety/refusal behavior, latency, and runtime stability.

The headline question is:

> Given this Hermes configuration, does the agent reliably reach useful,
> truthful, stable conclusions for real user requests?

HermesBench currently targets Hermes Agent users who customize a personal agent
for daily work: calendar, mail, messaging, web lookup, local context, finance,
travel, reports, and optional power-user integrations.

## What It Includes

- **27 bundled workflow recipes** across 9 job-area categories.
- **Harness-driven scenarios**: a use case can be one user turn or a multi-turn
  conversation in one isolated Hermes session.
- **Driver/target separation**: recipes define human-facing user jobs; run
  configuration chooses the driver and target agent adapter.
- **Flat recipe categories**: one visible grouping level for browsing,
  filtering, and optional batch runs.
- **Score-only verdict**: missed outcomes, instability, incomplete/false
  answers, and latency regressions are folded into one score plus axis
  diagnostics.
- **Explicit side-effect boundaries**: recipes are marked read-only,
  benchmark-local-write, or external-write-boundary. External changes require
  confirmation and should not be performed by bundled recipes.
- **Local suites**: users can add private JSON/YAML suites without changing
  HermesBench code.
- **Transparent public artifacts**: scenario recipes and public leaderboard
  evidence are generated for the repo and website.
- **Trend store**: runs persist to `$HERMES_HOME/hermesbench.db`.

## Framework Shape

HermesBench now treats a scenario as the runnable unit. The advocated default
is one scenario recipe; suites and the full bundled benchmark are opt-in because
they take longer and cost more. Suites are just grouped scenario collections:

```text
scenario spec -> driver adapter -> target adapter -> deterministic checks -> judge -> score
```

- **Scenario spec**: goal, `initial_prompt`, side-effect metadata, and optional
  artifact/scope checks.
- **Driver adapter**: orchestrates the scenario. The default is `codex`, which
  uses Codex headless mode as a bounded evaluator-side controller. It sends the
  initial prompt, may ask natural follow-up turns, and reports whether the
  scenario is closed.
- **Target adapter**: talks to the agent under test through a selected user
  interface. The default transport is Hermes CLI, but the same cases can run
  through simulated platform UIs such as Telegram/Weixin or a custom command
  bridge. Direct/no-kanban vs kanban delegation is run/profile config, not case
  data.
- **Tools/AgentSkills surface**: cases declare capability intent, and each run
  records the selected toolsets, platform toolsets, and AgentSkills inventory so
  score changes can be tied back to the configuration surface.
- **Scorer**: uses deterministic evidence plus bounded LLM judgement to decide
  whether the scenario reached a real outcome and whether the final result was
  complete, truthful, scoped, responsive, and clear.

## Published Baselines

The first public baselines are redacted distribution-style snapshots of the same
local Hermes default profile family. The leaderboard focuses on score-related
diagnostics and keeps reproducibility metadata in the linked baseline files.

| configuration | score | cap/truth | rel/safety | eff/ux | fulfillment | evidence | outcome | safety | response | comms | coverage | profile snapshot |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `verkyyi/default-no-kanban` | `78.15` | `70.9` | `96.2` | `86.6` | `71.6` | `69.9` | `94.2` | `98.1` | `92.2` | `80.9` | `13/14` | `direct`, `gpt-5.5`, `honcho`, `3 plugins` |
| `verkyyi/default` | `77.23` | `68.9` | `94.2` | `86.5` | `69.8` | `67.5` | `92.3` | `96.2` | `94.6` | `78.4` | `13/14` | `kanban`, `gpt-5.5`, `honcho`, `4 plugins` |

Outcome reached is evidence-grounded: a transport-level reply is not enough; the
driver/judge must see a valid terminal state. The opt-in `delegated_closure`
suite is not included in either baseline score. These baselines use the balanced
3x2 scoring model and were run in parallel with bounded high-rate concurrency.
They were captured before the bundled suite set shifted to the generic
personal-agent taxonomy, so refresh them before treating the displayed scores as
current leaderboard entries for the new public suite mix.

Each baseline directory includes a human summary plus public-safe observability
artifacts: `run-manifest.json`, `suite-results.json`, `case-results.jsonl`,
`judge-decisions.jsonl`, `artifact-manifest.json`, `cost-usage.json`,
`variance.json`, `profile-snapshot.redacted.yaml`, `score.json`, and
`distribution-baseline.yaml`.

Baseline directories:

- [`data/baselines/verkyyi-default-2026-05-29`](data/baselines/verkyyi-default-2026-05-29)
- [`data/baselines/verkyyi-default-no-kanban-2026-05-29`](data/baselines/verkyyi-default-no-kanban-2026-05-29)

Transparent recipe and leaderboard artifacts:

- [`docs/recipe-schema.md`](docs/recipe-schema.md): public draft of the
  authored recipe schema and feedback questions.
- [`data/tasks/README.md`](data/tasks/README.md): human-readable recipe catalog.
- [`data/tasks/tasks.json`](data/tasks/tasks.json): machine-readable scenario
  catalog with per-scenario public leaderboard rows.
- [`data/traces/index.json`](data/traces/index.json): published leaderboard
  evidence index.
- [`data/submissions/README.md`](data/submissions/README.md): public
  leaderboard submission contract.
- [`site/recipes.html`](site/recipes.html): website recipe browser.
- [`site/leaderboard.html`](site/leaderboard.html): website leaderboard.

Leaderboard evidence is public-safe by default: it shows the scenario, expected
outcome, score, axes, mechanical closure, driver decision, judge summary,
checks, side-effect manifest, and a PII-redacted public transcript when the run
captured one. Unredacted raw replies/transcripts are private debugging
artifacts; only retain them with `HERMES_BENCH_INCLUDE_RAW_TRACES=1`, and redact
before publishing.

Each scenario recipe also owns a small leaderboard derived from public evidence.
The recipe catalog can therefore be used as a recipe library: inspect the best
linked result for a scenario to see which profile/config performed best
against that exact spec.

HermesBench baseline submissions should ideally link an installable Hermes
profile distribution repo. Redacted distribution-style baselines are acceptable
when the profile contains private/local state that cannot be published.
If a baseline exercises kanban delegation or multi-worker execution, every
involved orchestrator/worker profile must be included as an installable
distribution or as a redacted distribution-style snapshot.

Public leaderboard submissions are also agent-driven. Ask a coding agent to use
the HermesBench skill workflow `Publish A Benchmark Result`; it will prepare a
directory under `data/submissions/<submitter>/<run-id>/`, validate redaction,
refresh public artifacts, and open a GitHub pull request when publication is
requested.

## Install

HermesBench requires a working Hermes Agent installation and the `hermes` CLI on
`PATH`.

```bash
pip install git+https://github.com/verkyyi/hermesbench.git
```

For local development:

```bash
git clone https://github.com/verkyyi/hermesbench.git
cd hermesbench
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Default Agent-Driven Quick Start

HermesBench is designed to be driven through a coding agent. The user-facing
path is: give the agent the HermesBench skill URL, let it install/import the
package, and let it call the Python API. Users should not orchestrate
HermesBench by copying command-line invocations.

```python
from hermesbench.api import agent_skill_path, list_scenarios, list_suites, run_scenario, validate

print(agent_skill_path())  # path to the packaged AgentSkill for the coding agent
print(validate())
print([suite["id"] for suite in list_suites()])
print([scenario["id"] for scenario in list_scenarios()[:5]])

report = run_scenario(
    "calendar_daily_brief",
    trials=1,
    run_llm_evals=True,
    target_ui="telegram",
    target_skills=["agentfeeds"],
    persist=False,
)
print(report["overall_score"])
```

The public AgentSkill is also browsable in the repo at
[`agent-skills/hermesbench/SKILL.md`](agent-skills/hermesbench/SKILL.md), and the
same file is packaged under `hermesbench.agent_skills` for installed users.

The API is the default surface for coding agents:

- `agent_skill_path()` / `agent_skill_text()`
- `list_scenarios(suite_path=None)`
- `list_suites(suite_path=None)`
- `validate(suite_path=None)`
- `run(..., scenarios=None, suites=None, full_bundle=False, trials=None, target_ui=None,
  target_toolsets=None, target_skills=None, persist=True, json_path=None)`
- `run_scenario(scenario_id, ...)`
- `recent_runs(limit=30)`
- `build_public_artifacts(repo_root=None)`

## Coding-Agent Controls

By default, `run()` uses the default scenario recipe `calendar_daily_brief`.
Use `run_scenario("...")` to name another recipe. To run every bundled suite,
pass `full_bundle=True`.

Concurrency controls:

- `trials=N` or `HERMES_BENCH_TRIALS`
- `case_concurrency=N` or `HERMES_BENCH_CONCURRENCY`
- `suite_concurrency=N` or `HERMES_BENCH_SUITE_CONCURRENCY`
- `high_rate=True`, which defaults to suite concurrency 6 and case concurrency
  6 unless the explicit values above are supplied

High-rate mode can create up to roughly 24 simultaneous prompt-case controllers
because each bundled suite has 4 cases. Use it only with provider credentials
that can tolerate the burst.

Public artifact generation is also API-driven:

```python
from hermesbench.api import build_public_artifacts

build_public_artifacts()
```

The default `codex` evaluator driver uses `codex exec` and may send follow-up
turns until it decides the scenario is closed or reaches its turn budget. Useful
driver controls:

- `HERMES_BENCH_AGENTIC_MAX_TURNS`: default dynamic budget for cases without an
  explicit `driver.max_turns` is 2
- `HERMES_BENCH_CODEX_MODEL` / `HERMES_BENCH_CODEX_PROFILE`: pin the evaluator
  controller model/profile
- `HERMES_BENCH_CODEX_TIMEOUT_S`: cap the controller wall time
- By default the Codex controller uses Codex bypass mode so the nested Hermes
  target bridge can make provider network calls from the benchmark-owned
  isolated `HERMES_HOME`. Set `HERMES_BENCH_CODEX_SANDBOX=workspace-write` to
  force Codex sandbox mode for controller-only experiments; target calls may
  fail if that sandbox blocks network access.

Target UI and capability controls:

- `target_ui="cli"`: default Hermes CLI transport to the target agent.
- `target_ui="telegram"` / `"weixin"` / another platform name: simulate that
  user interface by using its platform-scoped toolsets and skill filters
  without sending a real external message.
- `target_ui="command", target_command="..."`: run a custom target bridge. The
  scoped prompt is sent on stdin unless the command contains `{prompt}`. JSON
  stdout with `{"reply": "..."}` is accepted; plain stdout is also treated as
  the reply.
- `target_toolsets=["web", "skills"]`: override target toolsets for the run.
- `target_skills=["agentfeeds", "my-skill"]`: preload AgentSkills through the
  target Hermes transport.

Example platform/UI comparisons:

```python
from hermesbench.api import run

run(suites=["mail_assistant"], target_ui="cli", run_llm_evals=True)
run(suites=["mail_assistant"], target_ui="telegram", run_llm_evals=True)
run(
    suites=["general_assistant"],
    target_ui="command",
    target_command="./my-agent-ui --json",
    run_llm_evals=True,
)
```

## Bundled Categories

Bundled recipes use one visible grouping level: category. A category is both the
recipe-browser filter and the optional batch-run group. The recommended run unit
is still one scenario recipe, not a whole category.

Runtime suites such as `gateway_ack_policy` and `delegated_closure` are registered
separately because they need non-prompt harnesses. `delegated_closure` is the
kanban/multi-profile runtime suite for delegated work: it verifies that work
created from a user request can be picked up by the orchestrator path and still
reach user-visible closure. It skips cleanly when the corresponding Hermes Agent
internal modules or opt-in flags are unavailable.

```python
from hermesbench.api import run

report = run(
    suites=["delegated_closure"],
    run_llm_evals=True,
    persist=False,
)
```

## Local Suites

HermesBench is designed to be useful as a public benchmark and as a private
evaluation harness. Coding agents add local suites through `suite_path`:

```python
from hermesbench.api import list_suites, run, validate

suite_path = "examples/local_suites"
validate(suite_path=suite_path)
list_suites(suite_path=suite_path)
run(
    suite_path=suite_path,
    suites=["team_ops_status"],
    run_llm_evals=True,
    persist=False,
)
```

Local suite files can be JSON or YAML:

```json
{
  "categories": [
    {
      "id": "team_ops_status",
      "label": "Team ops status",
      "budget": {"reply_target_s": 35, "conclude_s": 150},
      "cases": [
        {
          "id": "release_unknown",
          "title": "Release readiness",
          "goal": "Help the user decide whether a release is safe to ship.",
          "initial_prompt": "Is the release safe to ship?",
          "effect_level": "external_write_boundary"
        }
      ]
    }
  ]
}
```

Local suites are not required to match bundled category sizes. They are for
user-specific regression coverage.

Recipes should use `initial_prompt` only, and the prompt should read like a
real user job rather than a trap or evaluator instruction. Shared reliability,
truthfulness, missing-access, and side-effect policy lives in the harness-level
judge instructions. Use optional criteria only when a local/private suite needs
constraints that do not fit naturally in the prompt, and use deterministic
checks only for machine-verifiable artifacts or scoped side effects. The
evaluator agent may drive safe follow-up turns when the target asks for missing
user information. Legacy `prompt` and `turns` fields still load for
compatibility.
Runtime suites can go further and drive multiple Hermes profiles, kanban,
gateways, or other auditable side-effect scopes.
Cases must not declare target surfaces such as direct/kanban; those are run
configuration and leaderboard metadata. Cases may declare capability metadata
such as expected toolsets, AgentSkills, and compatible interfaces; this is
coverage intent and observability metadata, not a hard requirement that couples
the case to one Hermes architecture.

## Side-Effect Policy

Default prompt suites run inside:

- a throwaway `HERMES_HOME`
- a benchmark-owned working directory
- `HERMES_BENCH_WORKDIR` pointing at that directory

The harness appends a side-effect scope note to each prompt. A default suite may
create or edit files only inside the benchmark workdir. It must not mutate real
user data, send messages, spend money, restart production services, or change
cloud infrastructure. Set `HERMES_BENCH_KEEP_ARTIFACTS=1` to retain workdirs for
debugging; otherwise HermesBench records an artifact manifest and cleans them up.
Profile snapshots redact secrets and local paths by default. Set
`HERMESBENCH_INCLUDE_PATHS=1` only for private debugging.

## Scoring

Per suite, HermesBench combines evidence-backed and judged signals:

- outcome reached
- evidence / truthfulness
- stability
- runtime / scope safety
- responsiveness
- task fulfillment
- communication quality

The default case formula is:

```text
score = 0.40 capability/truthfulness
      + 0.30 reliability/safety
      + 0.30 efficiency/UX

capability/truthfulness = 0.60 fulfillment + 0.40 evidence_truthfulness
reliability/safety      = 0.50 outcome     + 0.50 runtime_scope_safety
efficiency/UX           = 0.50 response    + 0.50 communication
```

HermesBench applies a balance factor across the three top axes, so a run with
similar capability, reliability, and UX scores ranks better than a lopsided run
with the same raw weighted average. Outcome and runtime/scope safety remain hard
gates: fast or polished replies score 0 if the scenario did not actually close,
crashed, or escaped the allowed side-effect scope. The final score is the only
product-facing verdict; axis scores explain why the score moved.

## Documentation

- [Methodology](docs/METHODOLOGY.md)
- [Roadmap](docs/ROADMAP.md)
- [Local suites guide](docs/local-suites.md)
- [Profile distribution baselines](docs/profile-distribution-baselines.md)
- [Website source](site/)

## Development

```python
from hermesbench.api import list_suites, validate

print(validate())
print(list_suites(suite_path="examples/local_suites"))
```

## Status

HermesBench is early and intentionally scoped to Hermes Agent users. The public
benchmark should stay stable, reproducible, and comparable; local suites are the
escape hatch for private workflows.
