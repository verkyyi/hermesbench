# HermesBench

HermesBench is a reliability-first benchmark and reusable evaluation harness for
**Hermes Agent runtime configurations**.

It is not a model leaderboard. The unit under test is the whole Hermes setup:
profile prompt, model/provider choice, tools, skills, memory, gateway behavior,
delegation/routing, safety/refusal behavior, latency, and runtime stability.

The headline question is:

> Given this Hermes configuration, does the agent reliably reach useful,
> truthful, stable conclusions for real user requests?

HermesBench currently targets Hermes Agent users, especially technical users who
use Hermes for code, ops, research, and agent-runtime work. It also includes a
small general-helper overflow package for normal assistant requests.

## What It Includes

- **48 bundled prompt use cases** across 12 balanced categories.
- **Harness-driven scenarios**: a use case can be one user turn or a multi-turn
  conversation in one isolated Hermes session.
- **Driver/target separation**: cases define user goals, fixtures, checks, and
  scoring intent; run configuration chooses the driver and target agent adapter.
- **4 audience packages**: technical operator, agent builder, knowledge worker,
  and general helper overflow.
- **Score-only verdict**: closure failures, instability, inappropriate answers,
  and latency regressions are folded into one score plus axis diagnostics.
- **Scoped side effects**: default prompt suites can write only inside a
  benchmark-owned working directory; live user data and external actions are
  opt-in only.
- **Local suites**: users can add private JSON/YAML suites without changing
  HermesBench code.
- **Trend store**: runs persist to `$HERMES_HOME/hermesbench.db`.

## Framework Shape

HermesBench now treats a case as a target-agnostic scenario:

```text
case spec -> driver adapter -> target adapter -> deterministic checks -> judge -> score
```

- **Case spec**: goal, `initial_prompt`/`prompt`/`turns`, optional fixture,
  deterministic checks, and scoring intent.
- **Driver adapter**: orchestrates the scenario. The default is `codex`, which
  uses Codex headless mode as a bounded evaluator-side controller. It sends the
  initial prompt, may ask natural follow-up turns, and reports whether the
  scenario is closed.
- **Target adapter**: talks to the agent under test. The current public adapter
  is Hermes CLI; direct/no-kanban vs kanban delegation is run/profile config,
  not case data.
- **Scorer**: uses deterministic evidence first and LLM judgement only for
  semantic appropriateness/coherence.

## Published Baselines

The first public baselines are redacted distribution-style snapshots of the same
local Hermes default profile family across two execution surfaces. The use cases
are framework-agnostic and run on both surfaces; the leaderboard exposes the
surface because Hermes with kanban and Hermes without kanban have materially
different configuration surfaces.

| configuration | target surface | evaluator | score | runtime | profile hash | bench git | run id |
|---|---|---|---:|---:|---|---|---|
| `verkyyi/default-no-kanban` | Direct/no-kanban | `legacy_static` | `91.76` | `~4m 50s` | `4080cb90` | `c14f160` | `hb-20260529T082033Z` |
| `verkyyi/default` | Kanban delegation | `legacy_static` | `89.78` | `~4m 0s` | `46baed47` | `c14f160` | `hb-20260529T081506Z` |

These checked-in rows are legacy static-evaluator baselines retained for
historical traceability. Current HermesBench prompt suites are agent-driven
only and use the Codex evaluator driver. The kanban baseline has `hermes-cli` +
`kanban` toolsets and `kanban-orchestrator-routing`; the no-kanban baseline
removes the kanban toolset, kanban config block, and kanban routing plugin. The
opt-in `delegated_closure` suite is not included in either baseline score.

Baseline files:

- [`data/baselines/verkyyi-default-2026-05-29/score.json`](data/baselines/verkyyi-default-2026-05-29/score.json)
- [`data/baselines/verkyyi-default-2026-05-29/distribution-baseline.yaml`](data/baselines/verkyyi-default-2026-05-29/distribution-baseline.yaml)
- [`data/baselines/verkyyi-default-2026-05-29/README.md`](data/baselines/verkyyi-default-2026-05-29/README.md)
- [`data/baselines/verkyyi-default-no-kanban-2026-05-29/score.json`](data/baselines/verkyyi-default-no-kanban-2026-05-29/score.json)
- [`data/baselines/verkyyi-default-no-kanban-2026-05-29/distribution-baseline.yaml`](data/baselines/verkyyi-default-no-kanban-2026-05-29/distribution-baseline.yaml)
- [`data/baselines/verkyyi-default-no-kanban-2026-05-29/README.md`](data/baselines/verkyyi-default-no-kanban-2026-05-29/README.md)

HermesBench baseline submissions should ideally link an installable Hermes
profile distribution repo. Redacted distribution-style baselines are acceptable
when the profile contains private/local state that cannot be published.
If a baseline exercises kanban delegation or multi-worker execution, every
involved orchestrator/worker profile must be included as an installable
distribution or as a redacted distribution-style snapshot.

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

## Quick Start

```bash
# List bundled suites.
hermesbench --list-suites

# Validate bundled and local suite definitions.
hermesbench --validate

# Cheap metadata/runtime-policy run. Prompt suites self-skip unless enabled.
hermesbench

# Full model-backed prompt run.
HERMES_RUN_LLM_EVALS=1 hermesbench

# Faster high-rate run. Use when your provider/key can handle the burst.
HERMES_RUN_LLM_EVALS=1 hermesbench --high-rate --trials 1

# Run only selected suites.
HERMES_RUN_LLM_EVALS=1 hermesbench --suite runtime_config,ambiguous_followup

# JSON output, no persistence.
HERMES_RUN_LLM_EVALS=1 hermesbench --json --no-store
```

Concurrency controls:

- `--trials N` or `HERMES_BENCH_TRIALS`
- `--case-concurrency N` or `HERMES_BENCH_CONCURRENCY`
- `--suite-concurrency N` or `HERMES_BENCH_SUITE_CONCURRENCY`
- `--high-rate`, which defaults to suite concurrency 4 and case concurrency 8
  unless the explicit flags above are supplied

High-rate mode can create many simultaneous Hermes and judge calls. Use it only
with provider credentials that can tolerate the burst.

The default `codex` evaluator driver uses `codex exec` and may send follow-up
turns until it decides the scenario is closed or reaches its turn budget. Useful
driver controls:

- `HERMES_BENCH_AGENTIC_MAX_TURNS`: default dynamic budget for cases without an
  explicit `driver.max_turns` is 3
- `HERMES_BENCH_CODEX_MODEL` / `HERMES_BENCH_CODEX_PROFILE`: pin the evaluator
  controller model/profile
- `HERMES_BENCH_CODEX_TIMEOUT_S`: cap the controller wall time
- By default the Codex controller uses Codex bypass mode so the nested Hermes
  target bridge can make provider network calls from the benchmark-owned
  isolated `HERMES_HOME`. Set `HERMES_BENCH_CODEX_SANDBOX=workspace-write` to
  force Codex sandbox mode for controller-only experiments; target calls may
  fail if that sandbox blocks network access.

## Bundled Suite Packages

| package | target user | suites |
|---|---|---|
| Technical operator | Developers/operators using Hermes for code, config, and system work | `runtime_config`, `code_workflow`, `ops_monitoring`, `tool_discipline` |
| Agent builder | Users shaping Hermes itself: benchmark, delegation, routing, gateway behavior | `benchmark_design`, `delegation_boundary`, `gateway_messaging` |
| Knowledge worker | Technical/product users asking for research, synthesis, memory-aware help, and decisions | `research_synthesis`, `memory_hygiene`, `truthfulness` |
| General helper overflow | Normal assistant usage outside the current technical-user core | `daily_assistant`, `ambiguous_followup` |

Runtime suites such as `gateway_ack_policy` and `delegated_closure` are registered
separately because they need non-prompt harnesses. `delegated_closure` is the
kanban/multi-profile runtime suite for delegated work: it verifies that work
created from a user request can be picked up by the orchestrator path and still
reach user-visible closure. It skips cleanly when the corresponding Hermes Agent
internal modules or opt-in flags are unavailable.

```bash
HERMES_RUN_LLM_EVALS=1 \
HERMES_BENCH_DELEGATED_CLOSURE=1 \
HERMES_BENCH_WORKER_PROFILES=orchestrator,worker-code,worker-research \
hermesbench --suite delegated_closure
```

## Local Suites

HermesBench is designed to be useful as a public benchmark and as a private
evaluation harness. Add local suites with `--suite-path` or
`HERMESBENCH_SUITE_PATH`:

```bash
hermesbench --suite-path examples/local_suites --list-suites
HERMES_RUN_LLM_EVALS=1 hermesbench --suite-path examples/local_suites --suite team_ops_status
```

Local suite files can be JSON or YAML:

```json
{
  "packages": {
    "team_ops": {
      "label": "Team ops",
      "description": "Private team workflows.",
      "categories": ["team_ops_status"]
    }
  },
  "categories": [
    {
      "id": "team_ops_status",
      "label": "Team ops status",
      "package": "team_ops",
      "budget": {"reply_target_s": 35, "conclude_s": 150},
      "cases": [
        {
          "id": "release_unknown",
          "expectation": "clarify",
          "initial_prompt": "Is the release safe to ship?",
          "notes": "No release evidence is provided; ask what to inspect."
        },
        {
          "id": "clarify_then_verify",
          "expectation": "task_done",
          "turns": [
            {"prompt": "Help me verify status."},
            {"prompt": "The target is the benchmark website deployment."}
          ],
          "notes": "The harness keeps both turns in one isolated session."
        }
      ]
    }
  ]
}
```

Local suites are not required to match the bundled 4-cases-per-category balance.
They are for user-specific regression coverage.

Prompt cases support either `prompt` for a single turn or `turns` for a
multi-turn conversation. Runtime suites can go further and drive multiple
Hermes profiles, kanban, gateways, or other auditable side-effect scopes.
Cases must not declare target surfaces such as direct/kanban; those are run
configuration and leaderboard metadata.

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

Per suite, HermesBench combines deterministic and judged signals:

- closure
- artifact correctness
- stability
- scope discipline
- responsiveness
- appropriateness
- coherence

Closure, stability, artifact checks, scope discipline, and responsiveness are
deterministic. Appropriateness and coherence come from the LLM judge. The final
score is the only product-facing verdict; axis scores explain why the score
moved.

## Documentation

- [Methodology](docs/METHODOLOGY.md)
- [Roadmap](docs/ROADMAP.md)
- [Local suites guide](docs/local-suites.md)
- [Profile distribution baselines](docs/profile-distribution-baselines.md)
- [Website source](site/)

## Development

```bash
pip install -e ".[dev]"
pytest
python -m hermesbench --validate
python -m hermesbench --suite-path examples/local_suites --list-suites
```

## Status

HermesBench is early and intentionally scoped to Hermes Agent users. The public
benchmark should stay stable, reproducible, and comparable; local suites are the
escape hatch for private workflows.
