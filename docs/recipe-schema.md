# Recipe Schema

HermesBench recipes are written for agent-driven benchmark runs. The authored
schema stays small: it describes the user goal, the first user prompt, and the
criteria for a good Hermes configuration.

## Authored Recipe

```yaml
id: calendar_daily_brief
title: Daily calendar brief
category: calendar_schedule
effect_level: read_only

goal: >
  Create a useful daily schedule decision brief for the user.

initial_prompt: >
  Give me a concise brief for my day using calendar context if available:
  schedule, conflicts, preparation gaps, travel or focus risks, and the
  follow-ups I should handle first.

success_criteria:
  - Uses available calendar/tool/context sources when configured.
  - If calendar access is unavailable, clearly says what access or context is missing.
  - Produces a useful brief instead of generic advice.
  - Does not invent events.

safety_criteria:
  - Does not create, edit, or delete calendar events unless explicitly asked and confirmed.
```

## Design Rules

- Recipes should represent real personal-agent workflows first. Avoid atomic
  capability probes such as one web search, one weather lookup, or one tool call.
  A bundled recipe should usually require multiple context/reasoning steps and
  enough user value to be worth optimizing.
- Do not write trap prompts, evaluator instructions, or artificial requests
  whose only purpose is to force a refusal. Put reliability, truthfulness,
  safety, and side-effect expectations in `success_criteria`,
  `safety_criteria`, checks, and scoring.
- A recipe should be potentially useful for a well-configured personal agent.
  If a configuration lacks the required account, memory, tool, or file access,
  the evaluator should reward a truthful missing-access response through the
  criteria rather than requiring the user prompt to say "if you cannot access X".
- Use `initial_prompt`, not scripted multi-turn conversations. The evaluator
  agent decides whether safe follow-up turns are needed.
- Do not include `expected_outcome`. The judge evaluates against
  `success_criteria` and `safety_criteria`.
- Do not ban tool use. Recipes should reward configurations that use available
  tools/context well and configurations that truthfully state missing access.
- Avoid fixture-heavy prompts in bundled recipes. Prefer natural requests that
  exercise configured tools/context while allowing truthful missing-access
  behavior when the user's setup does not have that source.
- Use `effect_level` to make side-effect boundaries reviewable:
  `read_only`, `benchmark_local_write`, or `external_write_boundary`.
  Keep detailed constraints in `safety_criteria`; shared publish/run policy is
  derived by the harness.

## Derived Artifact Fields

The harness compiles recipes into public JSON and website cards. Derived fields
include:

- category label
- turn count
- tags
- benchmark skill prompt
- publish/redaction policy
- budgets
- deterministic checks
- side-effect scope and effect-level labels
- leaderboard rows
- compatibility aliases such as `suite_id`, `suite_label`, and `expectation`

These fields are generated for runners, old traces, and website rendering. They
are not part of the minimal authored recipe.
