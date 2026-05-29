# verkyyi default baseline, 2026-05-29

This is the first published HermesBench baseline from a local Hermes default
profile. It is the **kanban delegation** surface for the same profile family;
see `../verkyyi-default-no-kanban-2026-05-29` for the paired direct/no-kanban
baseline.

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
| Run ID | `hb-20260529T081506Z` |
| Overall score | `89.78` |
| Observed runtime | `~4m 0s` |
| Evaluator driver | `legacy_static` |
| Profile hash | `46baed471e56051cba87b3cb67ac1d75c7a2bb97668570c51645832f34608377` |
| HermesBench git SHA | `c14f160b89a5828af70344df290f66d127bafed3` |
| Prompt cases | `48` |
| Suites ran | `13` |
| Trials per case | `1` |
| Suite concurrency | `4` |
| Case concurrency | `8` |

Command:

```bash
HERMES_RUN_LLM_EVALS=1 hermesbench --driver static --high-rate --trials 1
```

## Runtime Shape

| field | value |
|---|---|
| Model provider | `openai-codex` |
| Model | `gpt-5.5` |
| Memory | `honcho`, enabled |
| Execution surface | Kanban delegation |
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
`gateway_ack_policy`; `delegated_closure` was skipped because
`HERMES_BENCH_DELEGATED_CLOSURE` was not set.

Because worker profiles were not part of the measured path, their full profile
configs are not published in this baseline. If a future baseline runs delegated
or multi-worker suites, every involved orchestrator/worker profile must be
published as an installable Hermes profile distribution or as a redacted
distribution-style profile snapshot.

## Suite Scores

| suite | score |
|---|---:|
| `runtime_config` | 94.66 |
| `code_workflow` | 68.99 |
| `ops_monitoring` | 71.12 |
| `tool_discipline` | 98.81 |
| `benchmark_design` | 96.89 |
| `delegation_boundary` | 99.06 |
| `gateway_messaging` | 96.06 |
| `research_synthesis` | 94.00 |
| `memory_hygiene` | 98.06 |
| `truthfulness` | 93.44 |
| `daily_assistant` | 67.29 |
| `ambiguous_followup` | 88.76 |
| `gateway_ack_policy` | 100.00 |

`delegated_closure` was skipped because `HERMES_BENCH_DELEGATED_CLOSURE` was not set.

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
