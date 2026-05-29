# Recipe Schema

HermesBench recipes are written for agent-driven benchmark runs. The authored
schema stays small and human-facing: it describes the user goal and the first
user prompt. The harness-level judge policy handles shared truthfulness,
missing-access, and side-effect rules.

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
```

## Design Rules

- Recipes should represent real personal-agent workflows first. Avoid atomic
  capability probes such as one web search, one weather lookup, or one tool call.
  A bundled recipe should usually require multiple context/reasoning steps and
  enough user value to be worth optimizing.
- Do not write trap prompts, evaluator instructions, or artificial requests
  whose only purpose is to force a refusal. Put ordinary expectations in the
  natural user prompt; shared truthfulness and side-effect policy lives in the
  harness-level judge instructions.
- A recipe should be potentially useful for a well-configured personal agent.
  If a configuration lacks the required account, memory, tool, or file access,
  the evaluator should reward a truthful missing-access response through the
  criteria rather than requiring the user prompt to say "if you cannot access X".
- Use `initial_prompt`, not scripted multi-turn conversations. The evaluator
  agent decides whether safe follow-up turns are needed.
- Do not include `expected_outcome`. The judge infers the right outcome from
  the prompt, target configuration, transcript, and sanitized tool evidence.
- Do not ban tool use. Recipes should reward configurations that use available
  tools/context well and configurations that truthfully state missing access.
- Avoid fixture-heavy prompts in bundled recipes. Prefer natural requests that
  exercise configured tools/context while allowing truthful missing-access
  behavior when the user's setup does not have that source.
- Use `effect_level` to make side-effect boundaries reviewable:
  `read_only`, `benchmark_local_write`, or `external_write_boundary`.
- Use `success_criteria` or `safety_criteria` only for unusual local/private
  suites where the prompt cannot carry a constraint naturally.
- Use deterministic `checks` only for machine-verifiable artifacts or scoped
  side effects, such as `artifact_exists`; avoid keyword checks for
  conversational quality.

## Derived Artifact Fields

The harness compiles recipes into public JSON and website cards. Derived fields
include:

- category label
- turn count
- tags
- benchmark skill prompt
- publish/redaction policy
- budgets
- deterministic artifact/scope checks
- side-effect scope and effect-level labels
- leaderboard rows
- compatibility aliases such as `suite_id` and `suite_label`

These fields are generated for runners, old traces, and website rendering. They
are not part of the minimal authored recipe.
