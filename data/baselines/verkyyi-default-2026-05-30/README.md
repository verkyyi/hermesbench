# verkyyi default baseline, 2026-05-30

This is the current-taxonomy public baseline for the local Hermes default profile.
It replaces the 2026-05-29 legacy taxonomy baselines.

It is published as a **redacted distribution-style baseline**. It describes the
benchmark-relevant runtime configuration but is not an installable profile
distribution because the private profile contains local credentials, memories,
sessions, state, and personal skill allowlists.

## Result

| field | value |
|---|---:|
| Run ID | `hb-20260530T023418Z` |
| Overall score | `50.26` |
| Observed runtime | `~10m 35s` |
| Evaluator driver | `codex` |
| Profile hash | `e460b2161d64330938300535348c5819ca9b88c5848bdfb2b5f740acb66c1355` |
| HermesBench git SHA | `52fa6e382578fd034597acf0b3f74295230c55ce+dirty` |
| Prompt cases | `27` |
| Suites scored | `9/11` |
| Trials per case | `1` |
| Suite concurrency | `3` |
| Case concurrency | `3` |

Command:

```bash
HERMES_RUN_LLM_EVALS=1 python -m hermesbench.run --full-bundle --suite-concurrency 3 --case-concurrency 3 --trials 1 --json
```

## Score Breakdown

| metric | score |
|---|---:|
| capability truthfulness | 59.7 |
| efficiency ux | 50.2 |
| reliability safety | 70.4 |
| appropriateness | 59.7 |
| artifact correctness | 59.7 |
| closure | 70.4 |
| coherence | 69.6 |
| communication quality | 69.6 |
| evidence truthfulness | 59.7 |
| outcome reached | 70.4 |
| responsiveness | 30.9 |
| runtime scope safety | 70.4 |
| scope discipline | 100.0 |
| stability | 70.4 |
| task fulfillment | 59.7 |

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
| `general_assistant` | 69.33 |
| `calendar_schedule` | 71.78 |
| `web_research` | 20.08 |
| `daily_planning_reporting` | 41.68 |
| `mail_assistant` | 0.00 |
| `messaging_assistant` | 74.10 |
| `travel_places` | 46.59 |
| `personal_finance` | 73.81 |
| `developer_ops` | 55.01 |

## Skipped Suites

- `gateway_ack_policy`: Hermes Agent evals.responsiveness not importable: ModuleNotFoundError
- `delegated_closure`: HERMES_BENCH_DELEGATED_CLOSURE not set

`delegated_closure` remains opt-in because delegated/multi-profile execution
requires a broader public profile-distribution contract. `gateway_ack_policy`
skipped in this run because the local Hermes Agent runtime did not expose the
optional `evals.responsiveness` module.

## Redaction

The baseline omits auth material, `.env`, raw memories, sessions, state
databases, logs, private local paths, workspace contents, and personal skill
allowlists. Public transcripts and observability summaries are included only in
public-safe redacted form; raw target replies and controller outputs remain omitted.
