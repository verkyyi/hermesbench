# HermesBench — benchmark methodology (v2)

This document explains *what* HermesBench measures, *how* each number is
produced, and *how to read* the results. For run commands and operations see
[README.md](README.md).

---

## 1. What it is, and the philosophy

HermesBench is a **harness-driven reliability benchmark for Hermes profiles**.
The default public prompt suites drive the front-desk assistant the user
actually talks to and evaluate from the end user's perspective: send one or more
turns, observe what comes back. Runtime suites may add auditable internal checks
for behavior that is invisible from a single chat reply, such as kanban
delegated-closure preservation across multiple profiles.

### Positioning

HermesBench is **not a model leaderboard**. It is a **Hermes runtime
configuration benchmark**.

The unit under test is the whole Hermes agent setup: profile prompt,
model/provider choice, tool and skill configuration, memory configuration,
gateway/front-desk behavior, delegation/routing behavior, safety/refusal
behavior, latency, and reliability under the actual Hermes harness.

Hermes can expose very different configuration surfaces with and without
kanban. HermesBench keeps one leaderboard because the bundled prompt use cases
are framework-agnostic: they should run whether kanban is enabled or not. The
run metadata and public leaderboard must still surface the execution surface
(`kanban_delegation` vs `direct`) because kanban-enabled configurations may
perform better on delegation, progress, long-work closure, and async return-path
behavior, while direct/no-kanban configurations provide a simpler baseline.

The primary question is:

> Given this Hermes runtime configuration, does the agent reliably reach useful,
> truthful, stable conclusions for real user requests?

It is deliberately not trying to answer "is this base model smart?" or "can this
agent beat broad capability benchmarks?" External suites such as ClawBench,
SWE-bench, and Terminal-Bench are better suited for raw capability comparisons.
HermesBench should stay optimized for daily regression detection on Hermes
configuration quality.

Priority order:

1. **Reliability** — responds, concludes, and avoids silent drops, hangs,
   crashes, and dangling promises.
2. **Truthfulness / appropriateness** — answers when it should, clarifies when
   underspecified, refuses or admits uncertainty when it cannot know, and avoids
   fabrication.
3. **Stability** — behavior stays consistent across runs, config changes are
   attributable, and the harness remains healthy.
4. **Responsiveness** — latency remains usable and regressions are visible under
   comparable configuration.
5. **Capability** — useful but secondary; hard-task success belongs in external
   benchmarks or separate optional suites.

### Constraints

These constraints define what belongs in the default HermesBench surface.

Accept:

- A normal scheduled run finishes in less than 30 minutes on the target Hermes
  host.
- LLM/provider cost for a normal run stays below $10. Expensive or high-volume
  suites must be explicit opt-ins.
- Repeated runs for the same Hermes configuration vary only within a bounded
  noise floor. Regressions should be judged against trends or baselines, not a
  single noisy point.
- The benchmark applies to any Hermes configuration that can run the default
  profile. It must not require a specific base model, provider, memory backend,
  tool layout, or plugin set unless the suite is explicitly config-specific.
  Config-specific suites must declare and record the involved profiles.
- Use cases are parallelizable and isolated. They can run in throwaway
  `HERMES_HOME` state and benchmark-owned working directories without depending
  on shared mutable production state.
- The final result is a single score. Closure failures, instability,
  inappropriate answers, and refusals are consolidated into score and axis
  scores rather than a separate pass/fail verdict.
- Prompt cases may include side effects when the scope is user-acceptable,
  reversible, and auditable: benchmark-owned files, fixture data, or sandboxed
  state. Live end-to-end suites that send messages, mutate real data, spend
  money, or touch external services are opt-in and isolated.
- Each run records a redacted profile snapshot and harness fingerprint so trend
  changes can be explained without storing secrets, raw memory, or raw chats.
- Each run records the execution surface. Results from kanban-enabled and
  no-kanban profiles can share one leaderboard, but the surface must be visible
  next to the score.
- Test suites and use cases are easy to extend. HermesBench should be both a
  standard benchmark for Hermes harness quality and a reusable evaluation
  harness: adding a case or category should not require touching the runner,
  store, report, or dashboard.
- Test cases can be multi-turn conversations. The framework must evaluate the
  whole transcript and side-effect manifest, not only a single assistant reply.

Reject:

- Raw model leaderboards, broad capability races, or claims that the score
  measures only base-model intelligence.
- Scoring that depends on hidden internal mechanics such as kanban state,
  orchestrator routing internals, task links, or board implementation details
  for normal prompt cases. Runtime suites may inspect internals only when the
  suite is explicitly about that runtime contract and the side effects are
  isolated/auditable.
- Default cases that mutate real user data, send real messages, delete
  non-benchmark files, spend money, or change cloud infrastructure.
- Unscoped, irreversible, or unaudited side effects.
- Suites that make daily runs exceed the 30-minute or $10 default budget. Put
  them behind opt-in flags instead.
- Regression decisions based on a single flaky run without variance tracking,
  repeat trials, or historical baseline context.
- Tests that reward hard-task completion while ignoring closure, truthfulness,
  appropriateness, stability, and latency regressions.
- Prompts that require private memory facts, personal accounts, a specific
  provider, or a local machine setup unless they are clearly labeled as
  opt-in/config-specific suites.
- Bundled use cases that require kanban to exist. Kanban-specific checks belong
  in opt-in runtime suites such as `delegated_closure`.
- Unredacted storage of secrets, `.env` contents, raw profile config, raw memory,
  or raw chat transcripts.
- Non-parallelizable cases, cases that conflict through shared state, or cases
  whose result depends on execution order.
- Dashboard or report surfaces that expose multiple contradictory final
  verdicts. The score is the final result.
- Benchmark changes that require bespoke runner/store/dashboard code for every
  new ordinary use-case category.

1. **Harness-driven user view.** Drive the agent like a user; judge the reply or
   transcript. Prompt suites do not depend on hidden internals.
2. **Architecture-agnostic.** No assertions about internals. You can rip out and
   replace kanban/orchestrator and this benchmark still measures the same
   user-facing contract. (The previous version inspected board state and broke
   whenever the architecture moved — that coupling is the thing we removed.)
3. **Reliability > capability.** *Does it always respond, stay stable, feel
   responsive, and reach closure* matters more than *can it solve a hard
   problem.* Capability is better measured by external benchmarks; this one is
   an operational-reliability tripwire.
4. **Every prompt reaches a conclusion.** Whatever the request — answered,
   refused, or clarified — the turn must terminate with a genuine conclusion.
   Never a hang, crash, or silent drop. **Closure is the headline contract.**
   The published verdict is still one score: missed closure, instability, and
   inappropriate behavior reduce the score instead of creating a second
   pass/fail result.

### The harness-effect principle

Identical model weights swing 10–50 points across measurement harnesses, so a
*trend* benchmark must keep the harness fixed and record what it was. Every run
stamps a **harness fingerprint** (git sha, model id, profile hash) plus a
redacted **profile snapshot** of benchmark-relevant config; see §7.

---

## 2. Structure

```
usecases (dataset) ─┐
harness (drive) ────┼─► suites (one per category) ─► runner ─► store ─► report / JSON
judge (LLM verdict)─┘
```

- **`usecases.py`** — the dataset: scenarios grouped into categories, each with
  an `expectation` (the closure the user should get). A scenario may be a single
  `prompt` or a multi-turn `turns` list.
- **`harness.py`** — drives the default profile in an isolated single-turn or
  multi-turn session and returns the transcript + mechanical signals.
- **`judge.py`** — an LLM rules on the parts only judgement can assess.
- **`suites/usecases.py`** — one `run()` per category: drive + judge across
  trials, aggregate to `{score, metrics}`.
- **`registry.py`** — lists the categories as suites.
- **`run.py` / `store.py` / `report.py`** — execute, persist to a SQLite time
  series, render with deltas, and emit JSON for dashboards or external sites.

There is no pass/fail tier concept. Prompt suites are grouped by audience
package for coverage, not by difficulty. Model-backed suites **self-skip** when
`HERMES_RUN_LLM_EVALS` is unset; deterministic runtime-policy suites can still
run without model credentials.

---

## 3. Grading: mechanical core + LLM judge

A subtlety: "reliability > capability" and "embrace LLM judgement" are in mild
tension — the reliability signals (responded? how fast? crashed? concluded?) are
exactly what you want measured **deterministically**, not by a judge. So every
suite is **hybrid**:

- **Mechanical** (from the harness, deterministic): `responded`, time-to-first-
  answer (`ttfa_ms`), total latency (`ttlt_ms`), `stable` (no crash/timeout/
  error), `concluded` (a terminal reply arrived within budget).
- **LLM-judged** (from `judge.py`): `conclusion_type` ∈
  {`completed`, `rejected`, `clarification`, **`none`**}, `appropriate` (0–1,
  vs the case's expectation), `coherent` (0–1).

Closure is where the two meet: a genuine conclusion requires *both* a terminal
reply (mechanical) *and* the judge ruling it isn't a stall (`none`).

---

## 4. The black-box harness

For each prompt case the harness runs, in its **own throwaway `HERMES_HOME`**
(config + creds copied from the default profile) and a benchmark-owned working
directory:

```
hermes chat -q "<prompt>" --quiet
```

Single-turn cases run that command once. Multi-turn cases run one command per
declared user turn while preserving the same isolated `HERMES_HOME` and workdir,
so conversation state and scoped side effects can carry across the scenario.

It captures **stdout** (the reply) plus the per-home `telemetry.db` row
(`ttfa_ms`, `ttlt_ms`, status), wall-clock, and a small side-effect artifact
manifest for files created inside the benchmark working directory. Isolation
means runs do not need to touch real chats or the production board, and each run
gets an unambiguous latency row. (Same isolation pattern as
`evals/responsiveness/run_live`.)

The harness appends a benchmark scope note to each prompt and sets the process
working directory plus `HERMES_BENCH_WORKDIR` to the sandbox. Default prompt
suites may perform reversible/auditable side effects there. They must not send
external messages, mutate real user data, spend money, restart production
services, or change cloud infrastructure; those belong in explicit opt-in
runtime suites. By default the sandbox is cleaned up after the artifact manifest
is captured. Set `HERMES_BENCH_KEEP_ARTIFACTS=1` to retain it for debugging.

> **Runtime caveat.** Prompt scenarios still use synchronous `chat -q`, so they
> measure turn-terminal closure. Async worker-delegated closure (kanban → worker
> → async return) belongs in runtime suites. `delegated_closure` is the current
> opt-in kanban/multi-profile runtime suite; it uses isolated kanban state and
> records requested worker profile coverage. `chat -q` also has no gateway
> pre-LLM fast-ack, so the responsiveness signal is total time to the reply, not
> the sub-second front-desk ack (covered by `gateway_ack_policy`).

---

## 5. The judge

`judge.py` calls `agent.auxiliary_client.call_llm` (which auto-resolves the
default profile's provider/model, so the judge runs on the user's own model
family). It's told the case's `expectation` and rules:

- `conclusion_type` — `completed` / `rejected` / `clarification` / `none`.
  **`none`** is the failure: a stall, an empty/dangling reply, an "I'll get back
  to you" with nothing, or an off-topic non-answer.
- `appropriate` (0–1) — how well the behaviour matches the expectation (e.g. an
  *ambiguous* prompt should get `clarification`, not an invented answer; an
  *unknowable* prompt should be `rejected`, not fabricated).
- `coherent` (0–1) — clear, on-topic, non-contradictory.

An empty reply is ruled `none` without a model call. If the judge model itself
errors, that trial's judged axis is left unscored (`judge_error`) rather than
blamed on the agent.

---

## 6. Suites and use-case categories

Each prompt category is a suite (and a per-category dashboard trend).
Categories are balanced at 4 prompt cases each and grouped into audience
packages. Technical users are weighted as the main population today, while a
smaller general-helper overflow package keeps normal assistant usage covered.
`expectation` drives the judge's appropriateness ruling.

| Audience package | Target | Categories |
|------------------|--------|------------|
| Technical operator | Developers/operators using Hermes for code, config, and system work | `runtime_config`, `code_workflow`, `ops_monitoring`, `tool_discipline` |
| Agent builder | Users shaping Hermes itself: benchmark, delegation, routing, gateway behavior | `benchmark_design`, `delegation_boundary`, `gateway_messaging` |
| Knowledge worker | Technical/product users asking for research, synthesis, memory-aware help, and decisions | `research_synthesis`, `memory_hygiene`, `truthfulness` |
| General helper overflow | Normal assistant usage outside the current technical-user core | `daily_assistant`, `ambiguous_followup` |

| Category | Label | Expectation | Good closure |
|----------|-------|-------------|--------------|
| `runtime_config` | Runtime config | mixed | inspects or asks for live config evidence instead of guessing |
| `code_workflow` | Code workflow | mixed | handles review/debug/CI/file-work requests with scoped actions and verification discipline |
| `ops_monitoring` | Ops monitoring | mixed | reports status from evidence and avoids unsafe production actions |
| `tool_discipline` | Tool discipline | mixed | uses/avoids tools appropriately and respects safe-action boundaries |
| `benchmark_design` | Benchmark design | mixed | positions HermesBench as a runtime configuration benchmark with realistic constraints |
| `delegation_boundary` | Delegation boundary | mixed | handles small tasks inline and preserves the async return contract |
| `gateway_messaging` | Gateway messaging | mixed | preserves quote/reply context, ack/progress cadence, and platform norms |
| `research_synthesis` | Research synthesis | mixed | verifies current facts, synthesizes clearly, and states confidence |
| `memory_hygiene` | Memory hygiene | mixed | avoids stale-memory overreach and distinguishes temporary context |
| `truthfulness` | Truthfulness | mixed | avoids fabrication and states uncertainty/limits |
| `daily_assistant` | Daily assistant | mixed | handles ordinary helper requests without overclaiming live access |
| `ambiguous_followup` | Ambiguous follow-up | `clarify` | asks a focused question (`clarification`), doesn't guess missing context |

HermesBench also includes runtime suites that are not ordinary prompt
categories:

| Suite | What it measures | Default behavior |
|-------|------------------|------------------|
| `gateway_ack_policy` | Deterministic gateway pre-LLM ack/progress policy over emulated DM/group sessions | always runs; no model call |
| `delegated_closure` | Real kanban/multi-profile e2e check that delegated work keeps a user return path and records requested worker profile coverage | self-skips unless `HERMES_BENCH_DELEGATED_CLOSURE=1` and `HERMES_RUN_LLM_EVALS=1` |

Add cases by editing `usecases.py` (and a budget + label for a new category).

---

## 7. Scoring, verdict, and the fingerprint

**Per category** (over all its prompts × trials), weighting reliability far
above capability:

```
score = 100 · (0.40·closure_rate + 0.20·stable_rate
               + 0.15·responsiveness_mean + 0.25·appropriate_mean)
```

- `closure_rate` — fraction of trials reaching a genuine conclusion (mechanical
  concluded **and** judge ≠ `none`).
- `stable_rate` — fraction with no crash/timeout/error.
- `responsiveness_mean` — per trial, a time-to-reply score: 1.0 at/under the
  category's `reply_target_s`, decaying linearly to 0 at 3×. Uses telemetry
  `ttfa_ms` when present, else wall-clock. **`reply_target_s` is calibrated to
  the observed warm-steady-state p50**, so this score sits ~0.9 at baseline and
  measures *drift* — a latency regression drops it; the absolute latency is
  always reported separately as `wall_p50_ms`. A **per-process warm-up turn**
  (one throwaway tool-free turn before the measured ones, under a lock) absorbs
  cold-start so the score reflects warm latency — important because the 04:00
  cron runs cold. Disable with `HERMES_BENCH_WARMUP=0`.
- `appropriate_mean` — judge appropriateness over trials with a valid verdict.

That weighted value is the **base score**. The final score then applies
score-only penalties:

```
final_score = base_score
              · closure_rate
              · stable_rate
              · min(1, appropriate_mean / appropriateness_target)
```

This preserves a single result while keeping closure non-negotiable in practice:
a category with a missed conclusion or crash cannot keep a high score just
because other axes looked good. The default `appropriateness_target` is `0.7`.

**Overall score** = weighted mean of the categories that ran; suite errors score
0, while skipped suites drop out. **Fingerprint** per run:
`git_sha`, `model_id`, `profile_hash`, and a redacted `profile_snapshot` — so a
score move is attributable to the *change*, not the *measurement*. The snapshot
captures benchmark-relevant config shape and benchmark env vars; it excludes
secrets, raw `.env`, memory contents, chats, and local filesystem paths by
default. Set `HERMESBENCH_INCLUDE_PATHS=1` only for private debugging.

Trials default to 2 per case (`HERMES_BENCH_TRIALS`); concurrency
`HERMES_BENCH_CONCURRENCY` (default 4) controls prompt cases within a suite, and
`HERMES_BENCH_SUITE_CONCURRENCY` (default 1) controls suites across the run.
`--high-rate` sets suite concurrency 4 and case concurrency 8 unless explicit
flags override it. More trials = a steadier estimate on a
non-deterministic system, at more tokens/time.

---

## 8. Trend Store And Reporting

Runs append to **`$HERMES_HOME/hermesbench.db`** (SQLite, rollback journal +
`synchronous=FULL`, deliberately not WAL — avoids the torn-WAL-checkpoint
failure class, independent of the kanban kernel's own WAL).

The CLI prints a score-only report and can emit the full run JSON with `--json`.
The SQLite store keeps enough data for a dashboard or public leaderboard:
overall score, per-suite score, axis scores, suite metrics, harness fingerprint,
redacted profile snapshot, and execution surface.

**Reading a move:** overall down + one category down → localized; open the run
JSON (`--json`) for that category's `metrics` (closure/stable/appropriate +
`failures` sample + `conclusion_types`). A category flips to skip → creds
missing. Overall moved but no category did → check the fingerprint.

---

## 9. Known limitations

- **Gateway-chat watching remains future work.** Prompt scenarios can be
  multi-turn, and `delegated_closure` covers the kanban/orchestrator return path,
  but a live gateway watcher that observes user-visible async delivery is still
  separate future work.
- **Non-deterministic.** Real agent + LLM judge → run-to-run variance. Use more
  trials and read the trend, not a single run.
- **No token / cost instrumentation.** Cost ≈ (cases × trials) agent turns +
  one judge call each; not a measured dollar figure.
- **Judge shares the user's model family** (cheap + representative, but some
  self-grading bias; the rubric + low temperature mitigate it).
- **Small dataset** — a tripwire, not a comprehensive capability eval. Grow
  `usecases.py` over time.

---

## 10. Extending it

HermesBench is also meant to be a reusable evaluation harness, not just a fixed
benchmark. Ordinary prompt-suite extension should be data-only:

1. Add or edit cases in `usecases.py`, keeping each category at the balanced
   `CASES_PER_CATEGORY` count.
2. For a new category, add a `BUDGETS` entry, a `CATEGORY_LABELS` entry, and put
   the category in an `AUDIENCE_PACKAGES` list.
3. Run the focused HermesBench tests.

The registry builds suites from `usecases.categories()` automatically, and the
store/report/dashboard pick them up without bespoke code. Runtime suites that
need a custom harness, such as gateway probes, can still be added explicitly in
`registry.py`.

`tests/hermesbench/test_hermesbench.py` validates the registry, the judge parse/
coerce, the responsiveness curve, and the category scoring + closure gate (with
the harness and judge mocked — no real LLM) — extend it alongside any new suite.
