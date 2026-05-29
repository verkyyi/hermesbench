# verkyyi default no-kanban baseline, 2026-05-29

This baseline uses the same local Hermes default profile family as the kanban
baseline, but with the kanban execution surface disabled for the run.

It is published as a **redacted distribution-style baseline**. It is not an
installable profile distribution because the private profile contains personal
skills, local allowlists, credentials, memories, sessions, and state.

## Result

| field | value |
|---|---:|
| Run ID | `hb-20260529T082033Z` |
| Overall score | `91.76` |
| Observed runtime | `~4m 50s` |
| Evaluator driver | `static` |
| Profile hash | `4080cb90cb53240eb3ba53a210f9f57ed05a0c26f558ed81db37dc885c0cd9e4` |
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

The run used a temporary copied profile with `auth.json`, `.env`,
`config.yaml`, and `context_length_cache.yaml` copied from the private default
profile. The temporary config removed:

- `kanban` from `toolsets`
- `kanban` config block
- `kanban-orchestrator-routing` plugin

## Runtime Shape

| field | value |
|---|---|
| Model provider | `openai-codex` |
| Model | `gpt-5.5` |
| Memory | `honcho`, enabled |
| Execution surface | Direct/no-kanban |
| Toolsets | `hermes-cli` |
| Enabled plugins | `agentfeeds`, `break-glass-cli` |
| Kanban | disabled for this run |
| Gateway | recent-file trust enabled for 600 seconds |

## Why This Baseline Exists

Hermes with kanban and Hermes without kanban expose meaningfully different
shared configuration surfaces. The benchmark keeps one leaderboard because the
bundled use cases are framework-agnostic and should run on either surface, but
the leaderboard should make the surface visible next to the score.

The `delegated_closure` suite was skipped because
`HERMES_BENCH_DELEGATED_CLOSURE` was not set. That suite is kanban/multi-profile
specific and should be reported separately when included.

## Suite Scores

| suite | score |
|---|---:|
| `runtime_config` | 92.13 |
| `code_workflow` | 71.04 |
| `ops_monitoring` | 69.00 |
| `tool_discipline` | 94.20 |
| `benchmark_design` | 95.85 |
| `delegation_boundary` | 98.11 |
| `gateway_messaging` | 97.06 |
| `research_synthesis` | 95.94 |
| `memory_hygiene` | 93.19 |
| `truthfulness` | 98.72 |
| `daily_assistant` | 92.50 |
| `ambiguous_followup` | 95.08 |
| `gateway_ack_policy` | 100.00 |

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
