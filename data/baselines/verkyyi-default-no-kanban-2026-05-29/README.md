# verkyyi default no-kanban baseline, 2026-05-29

This baseline uses the same local Hermes default profile family as the kanban
baseline, but with the kanban execution surface disabled for the run. See
`../verkyyi-default-2026-05-29` for the paired baseline.

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
| Run ID | `hb-20260529T095156Z` |
| Overall score | `92.34` |
| Observed runtime | `~3m 46s` |
| Evaluator driver | `codex` |
| Agentic max turns default | `2` |
| Profile hash | `aa14b22a09265270b2552e98e6eaeade250578745443c14168c838cb8beec599` |
| HermesBench git SHA | `3a3893f36d7b7dc4aa172fe29b7b864bf4c34891` |
| Prompt cases | `48` |
| Suites ran | `13` |
| Trials per case | `1` |
| Suite concurrency | `6` |
| Case concurrency | `6` |

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
| Execution surface | Direct/no-kanban |
| Toolsets | `hermes-cli` |
| Enabled plugins | `agentfeeds`, `break-glass-cli`, `observability/langfuse` |
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
| `runtime_config` | 94.45 |
| `code_workflow` | 68.58 |
| `ops_monitoring` | 70.94 |
| `tool_discipline` | 97.88 |
| `benchmark_design` | 96.24 |
| `delegation_boundary` | 98.04 |
| `gateway_messaging` | 96.54 |
| `research_synthesis` | 95.75 |
| `memory_hygiene` | 93.83 |
| `truthfulness` | 99.05 |
| `daily_assistant` | 92.50 |
| `ambiguous_followup` | 96.56 |
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
