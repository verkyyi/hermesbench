# verkyyi default baseline, 2026-05-30

This is the current-taxonomy public baseline for the local Hermes default profile.
It replaces the earlier 2026-05-30 baseline run `hb-20260530T023418Z`.

It is published as a **redacted distribution-style baseline**. It describes the
benchmark-relevant runtime configuration but is not an installable profile
distribution because the private profile contains local credentials, memories,
sessions, state, and personal skill allowlists.

## Result

| field | value |
|---|---:|
| Run ID | `hb-20260530T220225Z` |
| Overall score | `78.20` |
| Stored runtime estimate | `~6m 18s` |
| Evaluator driver | `codex` |
| Profile hash | `27861f3a86d4aa0fcbaac0f2da0ba397842a2b05476e5a3383e5a5b3fb6926f2` |
| HermesBench git SHA | `e5e9cc40ba81b80b9ef38ba43d6ad59a81f3e9cf+dirty` |
| Prompt cases | `27` |
| Suites scored | `9/11` |
| Trials per case | `1` |
| Suite concurrency | `3` |
| Case concurrency | `3` |

Command:

```bash
HERMES_RUN_LLM_EVALS=1 python -m hermesbench.run --full-bundle --suite-concurrency 3 --case-concurrency 3 --trials 1 --json
```

Runtime note: Lower-bound runtime from the longest stored suite duration; global wall-clock was not captured in the trend store.

## Score Breakdown

| metric | score |
|---|---:|
| capability truthfulness | 80.7 |
| efficiency ux | 83.4 |
| reliability safety | 78.4 |
| appropriateness | 75.8 |
| artifact correctness | 75.8 |
| closure | 85.2 |
| coherence | 83.4 |
| communication quality | 83.4 |
| evidence truthfulness | 75.8 |
| outcome reached | 85.2 |
| responsiveness | 20.1 |
| runtime scope safety | 85.2 |
| scope discipline | 100.0 |
| stability | 85.2 |
| task fulfillment | 75.8 |

## Runtime Shape

| field | value |
|---|---|
| Model provider | `openai-codex` |
| Model | `gpt-5.5` |
| Memory | `honcho`, enabled |
| Execution surface | `Kanban delegation` |
| Toolsets | `hermes-cli, kanban` |
| Enabled plugins | `agentfeeds, break-glass-cli, kanban-orchestrator-routing, observability/langfuse` |
| AgentSkill inventory | `107` skills, hash `3760ef5a8871fc35` |

## Suite Scores

| suite | score |
|---|---:|
| `general_assistant` | 94.78 |
| `calendar_schedule` | 91.85 |
| `web_research` | 85.77 |
| `daily_planning_reporting` | 67.99 |
| `mail_assistant` | 83.20 |
| `messaging_assistant` | 96.79 |
| `travel_places` | 31.57 |
| `personal_finance` | 91.13 |
| `developer_ops` | 60.68 |

## Skipped Suites

- `gateway_ack_policy`: Hermes Agent evals.responsiveness not importable: ModuleNotFoundError
- `delegated_closure`: HERMES_BENCH_DELEGATED_CLOSURE not set

`delegated_closure` remains opt-in because delegated/multi-profile execution
requires a broader public profile-distribution contract. `gateway_ack_policy`
skipped in this run because the local Hermes Agent runtime did not expose the
optional `evals.responsiveness` module.

## Redaction

The baseline omits auth material, `.env`, raw memories, sessions, state
databases, logs, private local paths, workspace contents, personal skill
allowlists, and raw tool arguments/results. Public transcripts and observability
summaries are included only in public-safe redacted form; raw target replies and
controller outputs remain omitted.
