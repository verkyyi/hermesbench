# verkyyi default baseline, 2026-05-29

This is the first published HermesBench baseline from a local Hermes default
profile.

It is published as a **redacted distribution-style baseline**. It follows the
Hermes profile-distribution shape enough to describe the runtime configuration,
but it is not an installable profile distribution because the private profile
contains personal skills, local allowlists, credentials, memories, sessions, and
state that must not be shipped.

For installable public agents, publish a separate Hermes profile distribution
repository and link it from the benchmark result.

## Result

| field | value |
|---|---:|
| Run ID | `hb-20260529T062018Z` |
| Overall score | `81.95` |
| Observed runtime | `~2m 50s` |
| Prompt cases | `48` |
| Suites ran | `13` |
| Trials per case | `1` |
| Suite concurrency | `4` |
| Case concurrency | `8` |

Command:

```bash
HERMES_RUN_LLM_EVALS=1 hermesbench --high-rate --trials 1
```

## Runtime Shape

| field | value |
|---|---|
| Model provider | `openai-codex` |
| Model | `gpt-5.5` |
| Memory | `honcho`, enabled |
| Toolsets | `hermes-cli`, `kanban` |
| Enabled plugins | `agentfeeds`, `kanban-orchestrator-routing`, `break-glass-cli` |
| Kanban | dispatch in gateway, orchestrator profile, auto-decompose |
| Gateway | recent-file trust enabled for 600 seconds |

## Worker Profile Coverage

Kanban was enabled in this runtime configuration, and local worker-style
profiles were present:

- `orchestrator`
- `worker`
- `worker-code`
- `worker-fast`
- `worker-ops`
- `worker-report`
- `worker-research`

However, this baseline did **not** exercise multi-worker execution. The measured
run used the default/front-desk prompt suites plus deterministic
`gateway_ack_policy`; `origin_return` was skipped because
`HERMES_BENCH_ORIGIN_RETURN` was not set.

Because worker profiles were not part of the measured path, their full profile
configs are not published in this baseline. If a future baseline runs delegated
or multi-worker suites, every involved orchestrator/worker profile must be
published as an installable Hermes profile distribution or as a redacted
distribution-style profile snapshot.

## Suite Scores

| suite | score |
|---|---:|
| `runtime_config` | 68.38 |
| `code_workflow` | 37.10 |
| `ops_monitoring` | 92.73 |
| `tool_discipline` | 97.19 |
| `benchmark_design` | 91.83 |
| `delegation_boundary` | 97.19 |
| `gateway_messaging` | 95.00 |
| `research_synthesis` | 84.73 |
| `memory_hygiene` | 55.23 |
| `truthfulness` | 97.19 |
| `daily_assistant` | 60.23 |
| `ambiguous_followup` | 88.59 |
| `gateway_ack_policy` | 100.00 |

`origin_return` was skipped because `HERMES_BENCH_ORIGIN_RETURN` was not set.

## Redaction

The baseline omits:

- `auth.json`
- `.env`
- memories and sessions
- state databases
- logs
- workspace files
- local paths
- personal skill allowlists

See `distribution-baseline.yaml` for the machine-readable profile snapshot and
`score.json` for the machine-readable benchmark result.
