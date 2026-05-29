---
name: hermesbench
description: Use when a user wants to run, compare, validate, inspect, or extend HermesBench through a coding agent. Provides the Python API workflow, safe defaults, suite selection, target UI/tool/AgentSkill controls, and result interpretation.
version: 1.0.0
author: HermesBench maintainers
license: MIT
metadata:
  hermes:
    tags: [hermesbench, benchmark, evaluation, hermes-agent, agentskills]
    related_skills: [hermes-agent, codex]
---

# HermesBench Coding-Agent Driver

## Overview

HermesBench is a Python package and benchmark harness for Hermes Agent runtime
configurations. Use this skill to drive HermesBench from a coding agent without
asking the user to operate commands. The package API in `hermesbench.api` is the
only user-facing pathway described by this skill. If a command-line wrapper
exists in the package, treat it as an internal/developer implementation detail,
not as something the user should operate.

The benchmark measures the whole Hermes configuration: profile prompt,
provider/model choice, tools, AgentSkills, memory, gateway behavior,
delegation/routing, safety, latency, and stability. It is not a base-model
leaderboard.

## When To Use

- The user asks to run HermesBench, validate suites, inspect scores, compare two
  Hermes configurations, or publish a baseline.
- The user wants to submit a benchmark result to the public HermesBench
  leaderboard.
- The user wants to evaluate whether a Hermes customization improved a personal
  agent.
- The user wants a local/private suite loaded from JSON/YAML.
- The user wants a target UI comparison such as Hermes CLI transport vs
  Telegram-like platform toolsets.

Do not use this skill for unrelated benchmarks such as SWE-bench, Terminal-
Bench, or ClawBench unless the user is explicitly comparing methodology.

## Install Or Import

If the package is already installed:

```python
import hermesbench
```

If not installed, use the public package source URL:

```bash
python -m pip install git+https://github.com/verkyyi/hermesbench.git
```

For a checked-out repo, prefer editable install:

```bash
python -m pip install -e ".[dev]"
```

## Python API

Use these functions:

```python
from hermesbench.api import (
    agent_skill_path,
    agent_skill_text,
    build_public_artifacts,
    list_scenarios,
    list_suites,
    recent_runs,
    run,
    run_scenario,
    run_scenario_baseline,
    summarize_report,
    validate,
)
```

The Python package also ships this AgentSkill:

```python
from hermesbench.api import agent_skill_path, agent_skill_text

print(agent_skill_path())
skill_markdown = agent_skill_text()
```

List scenarios and suites:

```python
from hermesbench.api import list_scenarios, list_suites

for scenario in list_scenarios()[:10]:
    print(scenario["id"], scenario["category_label"], scenario["initial_prompt"])

for suite in list_suites():
    print(suite["id"], suite["interaction"], suite["category"])
```

Validate bundled and local suites:

```python
from hermesbench.api import validate

summary = validate()
print(summary)
```

Run one scenario without persistence:

```python
from hermesbench.api import run_scenario

report = run_scenario(
    "calendar_daily_brief",
    trials=1,
    run_llm_evals=True,
    persist=False,
)
print(report["overall_score"])
```

Run one scenario as a current-configuration baseline with the standard compact
summary:

```python
from hermesbench.api import run_scenario_baseline

baseline = run_scenario_baseline(
    "calendar_daily_brief",
    trials=1,
    run_llm_evals=True,
    target_ui="cli",
    target_profile="default",
    persist=True,
)
print(baseline["summary"])
```

Run selected suites and persist to the trend store. Suites aggregate the same
scenario runner primitive:

```python
from hermesbench.api import run

report = run(
    suites=["general_assistant", "mail_assistant"],
    trials=1,
    case_concurrency=2,
    suite_concurrency=2,
    run_llm_evals=True,
    persist=True,
)
```

Load local suites:

```python
from hermesbench.api import run, validate

suite_path = "./my-hermesbench-suites"
print(validate(suite_path=suite_path))
report = run(
    suite_path=suite_path,
    suites=["my_private_suite"],
    run_llm_evals=True,
    persist=False,
)
```

## Target UI And Capability Surface

HermesBench cases stay target-agnostic. The run chooses the target UI and
capabilities.

Default Hermes CLI transport. Keep this as the default for Hermes profile
quality because it is the smallest faithful target: it exercises the same
Hermes profile prompt, model/provider, tools, AgentSkills, memory, and session
state without depending on a bespoke wrapper. The CLI harness resumes the same
Hermes session across target turns, so every recipe should be treated as a
multi-turn conversation even when it closes after the first turn.

```python
report = run(
    suites=["general_assistant"],
    target_ui="cli",
    target_profile="default",
    run_llm_evals=True,
    persist=False,
)
```

Simulate a messaging platform surface without sending real messages. This uses
the platform-scoped Hermes toolsets and skill filters. Use this for Telegram,
Weixin, or other platform capability comparisons when live delivery is not the
thing under test:

```python
report = run(
    suites=["mail_assistant"],
    target_ui="telegram",
    target_profile="default",
    trials=1,
    run_llm_evals=True,
    persist=False,
)
```

Override target toolsets and preload AgentSkills:

```python
report = run(
    suites=["general_assistant"],
    target_toolsets=["web", "skills", "memory"],
    target_skills=["agentfeeds"],
    trials=1,
    run_llm_evals=True,
    persist=False,
)
```

Drive another UI or wrapper via a command bridge. The scoped prompt is sent on
stdin unless the command contains `{prompt}`. JSON stdout with a `reply` field
is accepted; plain stdout is treated as the reply. Use `target_ui="command"`
for a real gateway/channel bridge or non-CLI target only when the user asks to
test that transport. Do not make command the default: commands are
environment-specific, may hide channel credentials or delivery semantics, and
are harder to compare across machines unless the bridge is versioned and
declared.

```python
report = run(
    suites=["general_assistant"],
    target_ui="command",
    target_command="./my-agent-ui --json",
    trials=1,
    run_llm_evals=True,
    persist=False,
)
```

## Reading Results

Use `overall_score` as the final result. Axis scores explain why it moved.

Important report fields:

- `overall_score`: final score over suites that ran.
- `suites[*].score`: per-suite score.
- `suites[*].metrics.top_axis_scores`: capability/truthfulness,
  reliability/safety, efficiency/UX.
- `suites[*].metrics.axis_scores`: six sub-axes plus compatibility aliases.
- `harness.profile_snapshot.capability_surface`: target UI, target profile,
  selected platform, toolsets, AgentSkills inventory hash/count,
  disabled/allowed skill filters.
- `harness.git_sha`, `model_id`, `profile_hash`: reproducibility fingerprint.

Outcome reached is stricter than "the agent replied." The driver and judge must
see a valid terminal answer, refusal, clarification, or scoped artifact result.

## Common User-Facing Workflows

When a user pastes a short website prompt, infer the intended workflow here and
execute it end to end with the Python API.

### Run Current Hermes Configuration

Goal: produce a fast one-recipe local baseline for the currently active Hermes
profile. The whole bundled benchmark is opt-in.

Steps:

1. Use the active Hermes Python environment when it is discoverable. Prefer the
   interpreter in the `~/.local/bin/hermes` shebang or
   `~/.hermes/hermes-agent/venv/bin/python`, and verify it can
   `import hermes_cli`. Install HermesBench into that interpreter:

   ```bash
   uv pip install --python "$HERMES_PYTHON" git+https://github.com/verkyyi/hermesbench.git
   ```

   Fall back to a temporary virtualenv only when no active Hermes interpreter is
   available. Do not run the benchmark from an unrelated system Python; that can
   fail with `ModuleNotFoundError: No module named 'hermes_cli'` and wastes a
   persisted run.
2. Call `validate()` and report any suite definition errors before running.
3. If the user asks to run every recipe, all recipes, a full bundle, or a
   batch of recipes, ask for the target Hermes profile before starting. Use the
   coding-agent ask-question UI/tool when available (for Codex, use the
   available user-input/request tool); otherwise ask one concise question in
   chat. Do not ask again when the user already specified the profile or asked
   for the current/default profile.
4. Run `run_scenario_baseline("calendar_daily_brief", trials=1,
   run_llm_evals=True, target_ui="cli",
   target_profile="<chosen-or-default>", persist=True)` unless the user names a
   different recipe. If working from a checked-out HermesBench repo, the same
   workflow is available as `scripts/run_one_recipe_baseline.py`.
5. Do not run the whole bundled benchmark unless the user explicitly asks for a
   full-bundle run. Use `run(full_bundle=True, ...)` only for that opt-in path.
6. Summarize `overall_score`, top axes, six sub-axes, runtime, target UI,
   target profile, profile snapshot labels/tags, configured tools/toolsets,
   configured AgentSkills inventory/filter tags, observed tools/skills when the
   report exposes telemetry, redacted public transcript, skipped suites, and the
   most important failed cases. If observed tool/skill usage is empty, say it
   was not recorded rather than inferring it from transcript text. Do not print
   unredacted raw transcripts unless the run explicitly opted into raw trace
   retention.
7. Avoid dumping `recent_runs()` or large raw reports for a one-recipe result.
   Use `baseline["summary"]` or `summarize_report(report)` so the result shape
   is stable and fast to inspect.
8. Treat internal target warnings in the public transcript, such as auth
   fallback/model normalization/scanner warnings, as communication/UX findings
   when the judge flags them. Do not report them as failed deterministic checks
   unless they appear under `checks.failed`, `metrics.failures`, or suite
   `error`.
9. Call `build_public_artifacts()` in a checked-out repo when website/repo
   artifacts should be refreshed.

### Prepare A Publishable Baseline

Goal: turn a saved run into public artifacts suitable for review.

Steps:

1. Read the latest saved run or the baseline directory the user names.
2. Ensure the baseline has `run-manifest.json`, `score.json`,
   `suite-results.json`, `case-results.jsonl`, `judge-decisions.jsonl`,
   `profile-snapshot.redacted.yaml`, and trace artifacts.
3. Confirm public files do not contain secrets, raw memory, `.env`, auth
   material, private local paths, or unredacted personal data.
4. Regenerate public recipe and leaderboard artifacts with `build_public_artifacts()`.
5. Tell the user which artifacts are ready, which need manual review, and
   whether the result is comparable to the current bundled task taxonomy.

### Publish A Benchmark Result

Goal: prepare a public leaderboard submission through a GitHub pull request.

Use this workflow when the user asks to publish, submit, upload, or share a
HermesBench result publicly.

Steps:

1. Start from an existing publishable baseline directory or run the current
   Hermes configuration first if no run exists.
2. Read `data/submissions/README.md` from
   `https://github.com/verkyyi/hermesbench` for the current artifact contract.
3. Create a submission directory under
   `data/submissions/<submitter>/<run-id>/`.
4. Copy or generate the required public-safe artifacts:
   `submission.json`, `README.md`, `run-manifest.json`, `score.json`,
   `suite-results.json`, `case-results.jsonl`, `judge-decisions.jsonl`,
   `profile-snapshot.redacted.yaml`, and public trace artifacts.
5. Verify the submission:
   - required files exist
   - score and run id match across artifacts
   - suite taxonomy/version is current or clearly marked legacy
   - public transcript fields are redacted
   - no secrets, raw memory, `.env`, auth material, private local paths, or
     unredacted personal data are present
6. Regenerate public artifacts with `build_public_artifacts()`.
7. Prepare a concise PR summary with score, top axes, profile tags, run date,
   artifact directory, and manual-review notes.
8. Do not push branches, open PRs, or post externally unless the user explicitly
   asked for that publication action in the current conversation and the local
   policy allows it. If confirmation is needed, stop after preparing the branch
   and show the exact publish plan.

### Add A Private Local Suite

Goal: create private cases for the user's own Hermes workflow without changing
HermesBench runner/store/dashboard code.

Steps:

1. Draft a JSON/YAML local suite with target-agnostic cases.
2. Keep personal samples generic; do not put real private
   account data, secrets, contacts, or raw history into the suite file.
3. Make each `initial_prompt` read like a real user job, not a trap prompt or
   evaluator instruction.
4. Include `success_criteria`, `safety_criteria`, and deterministic checks only
   where practical; put reliability/truthfulness/safety expectations there, not
   in adversarial prompt wording.
5. Validate with `validate(suite_path=...)`.
6. Run one scenario first with `run(suite_path=..., scenarios=[...],
   trials=1, run_llm_evals=True, persist=False)`, then run the suite with `run(suite_path=..., suites=[...],
   trials=1, run_llm_evals=True, persist=False)` and report whether it is
   suitable for repeated local regression testing.

## Safe Defaults

- Use `persist=False` for exploratory runs.
- Use `trials=1` for smoke checks; increase trials for baseline quality.
- Use `scenarios=[...]` for the smallest focused check; use `suites=[...]` for
  grouped scenario runs before running the full benchmark.
- Do not enable opt-in runtime suites such as `delegated_closure` unless the
  user asked for multi-profile/kanban e2e checks.
- Public traces should contain redacted public transcripts when available.
- Do not publish raw profile config, unredacted raw transcripts, secrets, memory,
  or local paths.

## Common Pitfalls

1. Do not ask the user to run shell commands. Use the Python API yourself.
2. Do not interpret skipped suites as failures; skipped suites are excluded from
   `overall_score`.
3. Do not compare old baselines against a changed suite taxonomy without
   refreshing baselines.
4. Do not treat `target_ui="telegram"` as sending a Telegram message. It
   simulates the platform capability surface through the local target adapter.
5. Use `target_ui="command"` only for explicit real gateway/channel tests or
   custom wrappers. The bridge must preserve its own conversation state under
   `{workdir}` for multi-turn recipes and return JSON with a `reply` field when
   possible.
6. Do not expose `HERMES_BENCH_TARGET_COMMAND` contents if it may contain local
   secrets or tokens.

## Verification Checklist

- [ ] `validate()` returns `ok: True`.
- [ ] `list_suites()` includes the requested suite ids.
- [ ] A smoke `run(..., trials=1, persist=False)` returns an `overall_score` or
      clear skipped-suite reasons.
- [ ] The report's `capability_surface` matches the intended target UI,
      toolsets, and AgentSkills.
- [ ] Any published baseline includes redacted profile snapshot and score JSON.
