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

# Run only selected suites.
HERMES_RUN_LLM_EVALS=1 hermesbench --suite runtime_config,ambiguous_followup

# JSON output, no persistence.
HERMES_RUN_LLM_EVALS=1 hermesbench --json --no-store
```

## Bundled Suite Packages

| package | target user | suites |
|---|---|---|
| Technical operator | Developers/operators using Hermes for code, config, and system work | `runtime_config`, `code_workflow`, `ops_monitoring`, `tool_discipline` |
| Agent builder | Users shaping Hermes itself: benchmark, delegation, routing, gateway behavior | `benchmark_design`, `delegation_boundary`, `gateway_messaging` |
| Knowledge worker | Technical/product users asking for research, synthesis, memory-aware help, and decisions | `research_synthesis`, `memory_hygiene`, `truthfulness` |
| General helper overflow | Normal assistant usage outside the current technical-user core | `daily_assistant`, `ambiguous_followup` |

Runtime suites such as `gateway_ack_policy` and `origin_return` are registered
separately because they need non-prompt harnesses. They skip cleanly when the
corresponding Hermes Agent internal modules or opt-in flags are unavailable.

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
          "prompt": "Is the release safe to ship?",
          "notes": "No release evidence is provided; ask what to inspect."
        }
      ]
    }
  ]
}
```

Local suites are not required to match the bundled 4-cases-per-category balance.
They are for user-specific regression coverage.

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

Per suite, HermesBench combines mechanical and judged signals:

- closure
- stability
- responsiveness
- appropriateness
- coherence

The final score is the only product-facing verdict. Axis scores explain why the
score moved.

## Documentation

- [Methodology](docs/METHODOLOGY.md)
- [Roadmap](docs/ROADMAP.md)
- [Local suites guide](docs/local-suites.md)
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
