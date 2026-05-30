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
| Run ID | `hb-20260530T011046Z` |
| Overall score | `59.72` |
| Observed runtime | `~9m 45s` |
| Evaluator driver | `codex` |
| Profile hash | `e460b2161d64330938300535348c5819ca9b88c5848bdfb2b5f740acb66c1355` |
| HermesBench git SHA | `37097ee8194a59a63140deac36820234e803ccb6` |
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
| capability truthfulness | 56.5 |
| reliability safety | 92.6 |
| efficiency ux | 47.3 |
| task fulfillment | 56.5 |
| evidence truthfulness | 56.5 |
| outcome reached | 92.6 |
| runtime scope safety | 92.6 |
| responsiveness | 24.8 |
| communication quality | 69.8 |
| closure | 92.6 |
| artifact correctness | 56.5 |
| stability | 92.6 |
| scope discipline | 100.0 |
| appropriateness | 56.5 |
| coherence | 69.8 |

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
| `general_assistant` | 64.54 |
| `calendar_schedule` | 64.09 |
| `web_research` | 57.15 |
| `daily_planning_reporting` | 55.18 |
| `mail_assistant` | 40.10 |
| `messaging_assistant` | 73.23 |
| `travel_places` | 77.27 |
| `personal_finance` | 66.18 |
| `developer_ops` | 39.77 |

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
allowlists. Public transcripts are included after manual redaction of local paths and
secret names. Raw observability payloads remain omitted because they include
command arguments and tool results beyond the user-visible transcript.
