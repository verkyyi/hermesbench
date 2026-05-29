# HermesBench — actionable future work

Prioritized improvements identified while building/validating the benchmark.
Each item: **why**, **approach**, **effort**. The bench is fully usable without
any of these — they sharpen it. See [METHODOLOGY.md](METHODOLOGY.md) for the
design these build on.

---

## P1 — faithful responsiveness (the real gap)

**Status:** partially addressed. `gateway_ack_policy` now brings the
deterministic gateway ack/progress policy into HermesBench, but it still does
not measure the live gateway's actual ack bubble latency.

**Gateway-TTFA probe.** The isolated `chat -q` harness measures total-turn
wall-time, which is irreducibly noisy (host + provider variance) and **cannot
capture the real sub-300ms gateway pre-LLM ack** the user actually feels — the
thing "responsiveness" should mean here.
- **Why:** responsiveness is a top-priority axis but is currently a coarse,
  noisy proxy (see METHODOLOGY §9 + the 2026-05-28 validation: prompt suites
  swung 22s→67s between runs).
- **Approach:** a *separate* probe that sends a message through the real gateway
  to a dedicated test chat id and measures time-to-first-feedback (the ack
  bubble) and time-to-conclusion. Feed it as its own suite/category or a
  side-metric. Keep it isolated from real user chats (test chat id / sandbox).
- **Effort:** medium. Uses the gateway path (the one deliberately scoped out of
  the black-box harness), so it's additive, not a rewrite.

---

## P2 — coverage & trust

**Status:** partially addressed. The prompt dataset grew from 9 to 48 cases
across balanced audience-packaged configuration-quality categories, prompt
cases can now be single-turn or multi-turn scenarios, and `delegated_closure` is
available as an opt-in multi-profile e2e suite.

**Async-delegated closure harness.** The default prompt harness now supports
multi-turn `chat -q` scenarios, but it still can't verify that *async delegated*
work (kanban → worker → gateway return) actually comes back to the user — the
delegated-closure contract.
- **Why:** "every prompt reaches a conclusion" is the headline contract, but the
  delegated path is exactly where closure historically broke.
- **Approach:** `delegated_closure` now covers the delegated return-path and
  self-park contract with an isolated board and real agents when explicitly enabled.
  Remaining work: a true gateway-chat watcher that observes the final user
  message, not board state.
- **Effort:** medium-high.

**Grow the dataset.** 48 cases is a useful tripwire, not comprehensive coverage.
- **Why:** broader coverage + smoother per-category scores.
- **Approach:** continue adding scenarios to `usecases.py` — more
  scoped side-effect actions, over-delegation temptation, multi-turn requests,
  platform-specific return contracts, memory/tool edge cases, and safe refusal
  variety.
  The registry/store/dashboard pick up new categories automatically.
- **Effort:** low, ongoing.

**Independent judge.** The judge shares the user's model family (self-grading
bias; METHODOLOGY §9).
- **Approach:** pin a fixed judge model, or use a small multi-judge majority for
  contested verdicts. Keep temperature 0.
- **Effort:** low-medium.

---

## P3 — operations

**Regression alerting.** Today it's dashboard-trend-only.
- **Why:** the daily cron should *tell* you on a real regression, not wait to be
  looked at.
- **Approach:** after a run, compare vs rolling baseline; if a closure/stable
  rate drops, a conclusion-type flips, or overall moves beyond the **±1.2 noise
  floor**, push a message via the gateway. (Earlier scoped as dashboard-only —
  revisit.)
- **Effort:** low-medium.

**Token / cost instrumentation.** Cost-per-run is currently unknown (telemetry
records latency, not tokens).
- **Approach:** capture each spawned agent's usage (wrap the call path or read
  session usage) and store it alongside the score; surface cost on the dashboard.
- **Effort:** medium.

**Host-contention isolation.** Bench latency is contaminated by sharing the host
with the live gateway/workers.
- **Approach:** run the bench in a quiet window, lower its priority (nice), or a
  flag to pause worker dispatch during a run. Mainly helps the responsiveness
  axis; document either way.
- **Effort:** medium.

**Budget recalibration drift.** `reply_target_s` is calibrated to one sweep and
will drift as the model/profile changes.
- **Approach:** a periodic recalibration helper (or auto-baseline from the last
  N runs) so responsiveness keeps measuring drift, not absolute model speed.
- **Effort:** low.

**Variance / trials.** Single-run noise is real (esp. latency).
- **Approach:** raise `HERMES_BENCH_TRIALS` for tighter estimates; store per-run
  variance; optionally render error bars on the dashboard.
- **Effort:** low.

---

## Product findings surfaced by the bench (not bench work, but actionable)

- The front desk has historically over-used current-source lookup for simple
  prompts — worth checking whether the configuration reaches for tools only
  when the request actually needs them.
- The bench **caught a real `kanban.db` corruption** incident — keep the
  reliability axes as the live tripwire they proved to be.
