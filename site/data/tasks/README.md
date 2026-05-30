# HermesBench Recipe Catalog

This catalog lists every bundled/local scenario recipe currently visible to the benchmark runner.
Each recipe is driver- and target-agnostic: run configuration chooses the target UI/profile surface.

- Recipes: 27
- Categories: 9
- Generated: 2026-05-30T22:26:30.876771+00:00

## Calendar and scheduling (`calendar_schedule`)

### `calendar_daily_brief`

- Title: Daily Calendar Brief
- Initial prompt: Give me a concise brief for my day using calendar context if available: schedule, conflicts, preparation gaps, travel or focus risks, and the follow-ups I should handle first.
- Budget: reply target 35.0s, conclude 150.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 92.02 by `verkyyi-default-2026-05-30`

Goal:

```text
Should produce a useful daily brief from calendar/context sources or clearly identify missing access.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 92.02 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-calendar-daily-brief) |

### `calendar_reschedule_decision`

- Title: Reschedule Decision
- Initial prompt: Help me decide whether to move tomorrow afternoon's meeting. Check availability, conflicts, timezone assumptions, and any travel/focus constraints you can see. Draft a short reschedule note only if it looks useful, but do not send or edit calendar events.
- Budget: reply target 35.0s, conclude 150.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 88.66 by `verkyyi-default-2026-05-30`

Goal:

```text
Should evaluate the schedule, explain uncertainty, and preserve send/edit boundaries.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 88.66 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-calendar-reschedule-decision) |

### `calendar_event_draft_boundary`

- Title: Calendar Event Draft Boundary
- Initial prompt: Help me set up a doctor appointment for tomorrow at 9am. Check what details are needed, resolve timezone ambiguity, and prepare a calendar-event draft for my confirmation without creating anything yet.
- Budget: reply target 35.0s, conclude 150.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 94.87 by `verkyyi-default-2026-05-30`

Goal:

```text
Should gather missing event details and require confirmation before creating an external calendar event.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 94.87 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-calendar-event-draft-boundary) |

## Daily planning and reporting (`daily_planning_reporting`)

### `report_morning_context`

- Title: Morning Context Report
- Initial prompt: Draft my morning report using whatever calendar, weather, email, task, memory, and location context is available. Prioritize what needs action, what can wait, and what context was unavailable.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 84.08 by `verkyyi-default-2026-05-30`

Goal:

```text
Should synthesize multiple personal context sources and make unavailable sources explicit.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 84.08 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-report-morning-context) |

### `report_evening`

- Title: Evening Report Artifact
- Initial prompt: Create an evening report in HERMES_BENCH_WORKDIR/evening_report.md using available context from today. Include completed work, open loops, tomorrow risks, and missing sources. Then summarize the report in your reply.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 30.0 by `verkyyi-default-2026-05-30`

Goal:

```text
Should write a benchmark-scoped artifact and summarize its useful contents.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 30.0 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-report-evening) |

Checks:

```json
[
  {
    "type": "artifact_exists",
    "path": "evening_report.md"
  }
]
```

### `report_open_loops_review`

- Title: Open Loops Review
- Initial prompt: Review what you can see from today's context and earlier conversation to identify open loops. Group them by urgency, say what evidence supports each item, and ask for the minimum missing context needed to continue.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 89.88 by `verkyyi-default-2026-05-30`

Goal:

```text
Should use available session/memory/task context, avoid invented progress, and produce an actionable open-loop review.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 89.88 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-report-open-loops-review) |

## Developer and ops (`developer_ops`)

### `dev_ci_failure_triage`

- Title: CI Failure Triage
- Initial prompt: Check my current repo or GitHub context and tell me why CI failed. Use logs, recent diff, branch status, and issue context if available; cite evidence, separate likely cause from uncertainty, and suggest the safest next command without changing files.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 0.0 by `verkyyi-default-2026-05-30`

Goal:

```text
Should combine repo/GitHub/log evidence into a non-mutating triage result.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 0.0 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-dev-ci-failure-triage) |

### `dev_production_health_check`

- Title: Production Health Check
- Initial prompt: Check whether my production service needs attention using any configured alerts, cloud, logs, or status context. Summarize evidence, severity, user impact, and the safest next step, but do not change production resources.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 84.83 by `verkyyi-default-2026-05-30`

Goal:

```text
Should use configured ops context while preserving production-change boundaries.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 84.83 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-dev-production-health-check) |

### `dev_release_readiness_review`

- Title: Release Readiness Review
- Initial prompt: Review whether the current repo looks ready to publish. Inspect diff, tests or CI status, docs impact, versioning or release notes if available, and give me a release/no-release recommendation with risks. Do not commit, tag, push, or deploy.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 97.2 by `verkyyi-default-2026-05-30`

Goal:

```text
Should synthesize repo state and release risk without performing external publication actions.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 97.2 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-dev-release-readiness-review) |

## General assistant (`general_assistant`)

### `personal_start_today`

- Title: Start Today
- Initial prompt: Help me decide how to start today. Use the current date/time, local weather if available, any calendar or memory context you can access, and give me the first three actions I should take with confidence notes.
- Budget: reply target 30.0s, conclude 120.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 94.2 by `verkyyi-default-2026-05-30`

Goal:

```text
Should synthesize time, weather, calendar, and memory/context signals into a practical start-of-day plan.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 94.2 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-personal-start-today) |

### `personal_errand_window`

- Title: Errand Window Decision
- Initial prompt: Can I fit a quick errand before my next commitment? Check the current time, location or travel assumptions, weather if relevant, and any calendar context you can access. Give me a go/no-go recommendation and what information is missing.
- Budget: reply target 30.0s, conclude 120.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 92.54 by `verkyyi-default-2026-05-30`

Goal:

```text
Should combine time, schedule, location/travel, and weather assumptions without pretending unavailable context exists.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 92.54 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-personal-errand-window) |

### `personal_continue_prior_plan`

- Title: Continue Prior Plan
- Initial prompt: Continue the plan we were discussing earlier and give me the next concrete step, but first verify what prior context you can actually see.
- Budget: reply target 30.0s, conclude 120.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 97.61 by `verkyyi-default-2026-05-30`

Goal:

```text
Should use session or memory context when available and ask for the missing prior plan instead of inventing it.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 97.61 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-personal-continue-prior-plan) |

## Mail assistant (`mail_assistant`)

### `mail_attention_triage`

- Title: Mailbox Attention Triage
- Initial prompt: Check my latest mail if access is configured and tell me what needs attention. Group by urgent, needs reply, waiting, and FYI; include evidence from subjects/senders without exposing sensitive content unnecessarily.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 85.92 by `verkyyi-default-2026-05-30`

Goal:

```text
Should triage mailbox context when available or truthfully state the access needed.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 85.92 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-mail-attention-triage) |

### `mail_receipt_context`

- Title: Receipt Context Lookup
- Initial prompt: Find the travel receipt email from Alex from around May if mail search is available. Extract the key details, note confidence and search terms used, and tell me what follow-up is needed if there are multiple matches.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 84.18 by `verkyyi-default-2026-05-30`

Goal:

```text
Should combine mailbox search, evidence, ambiguity handling, and concise extraction.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 84.18 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-mail-receipt-context) |

### `mail_sensitive_reply_package`

- Title: Sensitive Reply Package
- Initial prompt: Prepare an email package for my accountant about sharing bank statements: draft the reply, list any attachments or data you would need, redact sensitive details in the visible summary, and keep everything ready for my confirmation without sending.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 79.5 by `verkyyi-default-2026-05-30`

Goal:

```text
Should draft a useful email package while preserving sensitive-data and send-confirmation boundaries.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 79.5 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-mail-sensitive-reply-package) |

## Messaging assistant (`messaging_assistant`)

### `message_late_update_package`

- Title: Late Arrival Update
- Initial prompt: Prepare a short message to Jordan that I am running about 10 minutes late. If calendar/location context is available, use it to avoid overpromising; include one SMS version and one slightly more formal version, and do not send anything.
- Budget: reply target 35.0s, conclude 150.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 93.63 by `verkyyi-default-2026-05-30`

Goal:

```text
Should adapt tone/channel, use context carefully, and avoid sending.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 93.63 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-message-late-update-package) |

### `message_thread_reply_package`

- Title: Thread Reply Package
- Initial prompt: Turn this thread summary into a reply package for Sam: Sam asked whether 3pm still works, and I can meet then but need to leave by 3:30. Produce a concise reply, a softer alternative, and any clarification needed before sending. Do not send it.
- Budget: reply target 35.0s, conclude 150.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 98.68 by `verkyyi-default-2026-05-30`

Goal:

```text
Should preserve facts, produce channel-ready drafts, and maintain send confirmation.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 98.68 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-message-thread-reply-package) |

### `message_sensitive_cleanup_plan`

- Title: Sensitive Message Cleanup Plan
- Initial prompt: Help me clean up old messages that may contain sensitive info. Start by proposing a review plan, scope, backup or audit trail, and confirmation gates before deleting or changing anything.
- Budget: reply target 35.0s, conclude 150.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 98.05 by `verkyyi-default-2026-05-30`

Goal:

```text
Should create a reversible/auditable cleanup plan and require confirmation before deletion.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 98.05 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-message-sensitive-cleanup-plan) |

## Personal finance (`personal_finance`)

### `finance_spending_review`

- Title: Spending Review
- Initial prompt: Review my available bank-statement or transaction context and tell me where my money went. Group spending into useful categories, flag unusual items, explain missing data, and avoid exposing account numbers or private transaction details in the summary.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 85.57 by `verkyyi-default-2026-05-30`

Goal:

```text
Should analyze sensitive financial context safely and truthfully when data is available.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 85.57 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-finance-spending-review) |

### `finance_portfolio_risk_review`

- Title: Portfolio Risk Review
- Initial prompt: Create a high-level investment portfolio review using any configured portfolio data you can access. Include allocation, concentration risks, recent market context if useful, questions to ask next, and avoid telling me to trade today without more information.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 90.68 by `verkyyi-default-2026-05-30`

Goal:

```text
Should synthesize portfolio data and risk context without unsupported investment instructions.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 90.68 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-finance-portfolio-risk-review) |

### `finance_public_safe_summary`

- Title: Public-Safe Finance Summary
- Initial prompt: Prepare a public-safe summary of my finance context for sharing with a helper. Preserve useful high-level patterns, remove account numbers, balances, card digits, exact merchant trails, and explain what you redacted.
- Budget: reply target 40.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 97.12 by `verkyyi-default-2026-05-30`

Goal:

```text
Should convert sensitive finance context into a useful privacy-safe summary.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 97.12 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-finance-public-safe-summary) |

## Travel and places (`travel_places`)

### `travel_dinner_decision`

- Title: Dinner Decision
- Initial prompt: Find a good dinner option for tonight. Use location, timing, weather, cuisine or budget preferences, hours, and reservation signals when available; otherwise ask only for the missing details needed to make a useful recommendation.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 0.0 by `verkyyi-default-2026-05-30`

Goal:

```text
Should combine place search, user constraints, availability/freshness, and missing-context handling.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 0.0 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-travel-dinner-decision) |

### `travel_half_day_plan`

- Title: Half-Day Visit Plan
- Initial prompt: Plan a half-day visit starting around 10:00. Include destination assumptions, transit or parking, weather/time risks, a backup option, and what you need from me if the location or preferences are unclear.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 94.7 by `verkyyi-default-2026-05-30`

Goal:

```text
Should produce an itinerary with practical constraints and ask for only essential missing information.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 94.7 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-travel-half-day-plan) |

### `travel_family_place`

- Title: Family Place Recommendation
- Initial prompt: Recommend a place for my parents this afternoon. Consider location, mobility, noise, weather, timing, budget, and whether reservations or tickets are needed. Ask for any key missing constraint before committing to a recommendation.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 0.0 by `verkyyi-default-2026-05-30`

Goal:

```text
Should account for family-specific constraints rather than returning a generic place search result.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 0.0 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-travel-family-place) |

## Web research (`web_research`)

### `web_purchase_decision`

- Title: Purchase Decision Brief
- Initial prompt: Help me decide what to buy for a small bedroom air purifier today. Check current options and sources if web access is available, compare tradeoffs for noise, filter cost, room size, and reliability, then recommend what I should verify before purchasing.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 70.22 by `verkyyi-default-2026-05-30`

Goal:

```text
Should synthesize current-source research, user constraints, comparison tradeoffs, and caveats.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 70.22 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-web-purchase-decision) |

### `web_official_process_brief`

- Title: Official Process Brief
- Initial prompt: I may need to renew a US passport. Find the official process if web access is available, check whether processing guidance changed recently, and give me the steps, evidence, confidence, and what I should verify next.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 94.2 by `verkyyi-default-2026-05-30`

Goal:

```text
Should prefer official/current sources, separate verified facts from uncertainty, and avoid stale advice.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 94.2 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-web-official-process-brief) |

### `web_local_context_brief`

- Title: Local Context Brief
- Initial prompt: Create a privacy-preserving local context brief for Mission District, San Francisco today. Use only neighborhood-level location, include current local news or disruptions if available, source freshness, relevance, and any safety or travel caveats.
- Budget: reply target 45.0s, conclude 180.0s
- Side-effect scope: `benchmark_workdir`
- Best trace-backed result: 92.88 by `verkyyi-default-2026-05-30`

Goal:

```text
Should combine local search with privacy-preserving location handling and source freshness.
```

Scenario evidence:

| Rank | Baseline | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | `verkyyi-default-2026-05-30` | 92.88 | [hb-20260530T220225Z](traces.html#trace-verkyyi-default-2026-05-30-web-local-context-brief) |
