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
| Run ID | `hb-20260529T111322Z` |
| Overall score | `77.23` |
| Observed runtime | `~7m 15s` |
| Evaluator driver | `codex` |
| Agentic max turns default | `2` |
| Profile hash | `e460b2161d64330938300535348c5819ca9b88c5848bdfb2b5f740acb66c1355` |
| HermesBench git SHA | `081c15983d45e82e5caead4e19e49e1652fba2c0+dirty` |
| Prompt cases | `48` |
| Suites ran | `13` |
| Trials per case | `1` |
| Suite concurrency | `3` |
| Case concurrency | `3` |

Command:

```bash
HERMES_RUN_LLM_EVALS=1 hermesbench --high-rate --suite-concurrency 3 --case-concurrency 3 --trials 1
```

## Score Breakdown

| metric | score |
|---|---:|
| Capability / truthfulness | 68.9 |
| Reliability / safety | 94.2 |
| Efficiency / UX | 86.5 |
| Task fulfillment | 69.8 |
| Evidence / truthfulness | 67.5 |
| Outcome reached | 92.3 |
| Runtime / scope safety | 96.2 |
| Responsiveness | 94.6 |
| Communication quality | 78.4 |

HermesBench uses a balanced 3x2 score model: capability/truthfulness 40%,
reliability/safety 30%, and efficiency/UX 30%. Each top axis has two sub-axes,
and a balance factor rewards configurations that stay strong across all three.

## Runtime Shape

| field | value |
|---|---|
| Model provider | `openai-codex` |
| Model | `gpt-5.5` |
| Memory | `honcho`, enabled |
| Execution surface | Kanban delegation |
| Toolsets | `hermes-cli`, `kanban` |
| Enabled plugins | `agentfeeds`, `break-glass-cli`, `kanban-orchestrator-routing`, `observability/langfuse` |
| Kanban | dispatch available |
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
| `runtime_config` | 79.62 |
| `code_workflow` | 59.87 |
| `ops_monitoring` | 52.75 |
| `tool_discipline` | 89.59 |
| `benchmark_design` | 60.13 |
| `delegation_boundary` | 90.84 |
| `gateway_messaging` | 85.89 |
| `research_synthesis` | 71.17 |
| `memory_hygiene` | 79.69 |
| `truthfulness` | 90.40 |
| `daily_assistant` | 63.10 |
| `ambiguous_followup` | 80.90 |
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

## Observability Artifacts

| file | purpose |
|---|---|
| `run-manifest.json` | Run identity, command, environment knobs, skipped suites, redaction policy, and file hashes. |
| `suite-results.json` | Per-suite scores, top axes, sub-axes, latency summaries, turns, judge errors, sampled failures, and side-effect samples. |
| `case-results.jsonl` | Redacted per-trial case observations; raw transcripts and target replies are omitted. |
| `judge-decisions.jsonl` | Aggregated LLM-judged metrics and sampled rationales; raw judge prompts/responses are omitted. |
| `artifact-manifest.json` | Benchmark-created side-effect files by relative path, size, and short hash; contents are not published. |
| `cost-usage.json` | Runtime and estimated call counts; token/cost accounting was not captured by this run. |
| `variance.json` | Single-run variance placeholder; repeated-run statistics are unavailable for this baseline. |
| `profile-snapshot.redacted.yaml` | Redacted runtime/profile snapshot extracted from the baseline. |
