# verkyyi default no-kanban baseline, 2026-05-29

This is the direct/no-kanban surface for the same profile family. See
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
| Run ID | `hb-20260529T111210Z` |
| Overall score | `78.15` |
| Observed runtime | `~6m 57s` |
| Evaluator driver | `codex` |
| Agentic max turns default | `2` |
| Profile hash | `aa14b22a09265270b2552e98e6eaeade250578745443c14168c838cb8beec599` |
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
| Capability / truthfulness | 70.9 |
| Reliability / safety | 96.2 |
| Efficiency / UX | 86.6 |
| Task fulfillment | 71.6 |
| Evidence / truthfulness | 69.9 |
| Outcome reached | 94.2 |
| Runtime / scope safety | 98.1 |
| Responsiveness | 92.2 |
| Communication quality | 80.9 |

HermesBench uses a balanced 3x2 score model: capability/truthfulness 40%,
reliability/safety 30%, and efficiency/UX 30%. Each top axis has two sub-axes,
and a balance factor rewards configurations that stay strong across all three.

## Runtime Shape

| field | value |
|---|---|
| Model provider | `openai-codex` |
| Model | `gpt-5.5` |
| Memory | `honcho`, enabled |
| Execution surface | Direct/no-kanban |
| Toolsets | `hermes-cli` |
| Enabled plugins | `agentfeeds`, `break-glass-cli`, `observability/langfuse` |
| Kanban | disabled |
| Gateway | recent-file trust enabled for 600 seconds |

## Worker Profile Coverage

Kanban was disabled for this runtime configuration. No worker profile path was
part of the measured baseline.

## Suite Scores

| suite | score |
|---|---:|
| `runtime_config` | 78.64 |
| `code_workflow` | 45.89 |
| `ops_monitoring` | 52.96 |
| `tool_discipline` | 89.09 |
| `benchmark_design` | 81.75 |
| `delegation_boundary` | 90.17 |
| `gateway_messaging` | 87.57 |
| `research_synthesis` | 80.29 |
| `memory_hygiene` | 69.19 |
| `truthfulness` | 88.27 |
| `daily_assistant` | 73.83 |
| `ambiguous_followup` | 78.31 |
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
