# verkyyi default baseline, 2026-05-29

This is the kanban delegation surface for the same profile family. See
`../verkyyi-default-no-kanban-2026-05-29` for the paired baseline.

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
| Run ID | `hb-20260529T094614Z` |
| Overall score | `88.82` |
| Observed runtime | `~5m 12s` |
| Evaluator driver | `codex` |
| Agentic max turns default | `2` |
| Profile hash | `e460b2161d64330938300535348c5819ca9b88c5848bdfb2b5f740acb66c1355` |
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

## Score Breakdown

| metric | score |
|---|---:|
| Closure | 96.2 |
| Stability | 96.2 |
| Scope discipline | 100.0 |
| Responsiveness | 88.0 |
| Appropriateness | 72.1 |
| Coherence | 81.2 |

Closure, stability, scope discipline, and responsiveness are deterministic
execution metrics. Appropriateness and coherence are LLM-judged semantic
metrics. Artifact correctness is retained in the machine-readable score file
and omitted from this compact table because it is currently saturated.

## Runtime Shape

| field | value |
|---|---|
| Model provider | `openai-codex` |
| Model | `gpt-5.5` |
| Memory | `honcho`, enabled |
| Execution surface | Kanban delegation |
| Toolsets | `hermes-cli`, `kanban` |
| Enabled plugins | `agentfeeds`, `break-glass-cli`, `kanban-orchestrator-routing`, `observability/langfuse` |
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
run used the standard prompt suites plus deterministic `gateway_ack_policy`;
`delegated_closure` was skipped because `HERMES_BENCH_DELEGATED_CLOSURE` was
not set.

Because worker profiles were not part of the measured path, their full profile
configs are not published in this baseline. If a future baseline runs delegated
or multi-worker suites, every involved orchestrator/worker profile must be
published as an installable Hermes profile distribution or as a redacted
distribution-style profile snapshot.

## Suite Scores

| suite | score |
|---|---:|
| `runtime_config` | 94.24 |
| `code_workflow` | 68.41 |
| `ops_monitoring` | 69.81 |
| `tool_discipline` | 97.45 |
| `benchmark_design` | 94.28 |
| `delegation_boundary` | 97.77 |
| `gateway_messaging` | 96.84 |
| `research_synthesis` | 95.81 |
| `memory_hygiene` | 73.62 |
| `truthfulness` | 98.51 |
| `daily_assistant` | 72.88 |
| `ambiguous_followup` | 95.06 |
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
