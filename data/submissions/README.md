# HermesBench Public Submissions

Public leaderboard submissions are repo-native and agent-driven. Users should
ask a coding agent to use the HermesBench skill, prepare the artifacts, and open
a GitHub pull request when ready.

Skill URL:

```text
https://github.com/verkyyi/hermesbench/blob/main/agent-skills/hermesbench/SKILL.md
```

## Directory Layout

Each submission lives under:

```text
data/submissions/<submitter>/<run-id>/
```

Example:

```text
data/submissions/acme/hb-20260601T120000Z/
```

## Required Files

- `submission.json`
- `README.md`
- `run-manifest.json`
- `score.json`
- `suite-results.json`
- `case-results.jsonl`
- `judge-decisions.jsonl`
- `profile-snapshot.redacted.yaml`
- public trace artifacts, either copied into the submission directory or linked
  from `submission.json`

## `submission.json`

```json
{
  "schema_version": 1,
  "submitter": "acme",
  "configuration_name": "Acme Hermes recommended",
  "run_id": "hb-20260601T120000Z",
  "submitted_at": "2026-06-01T12:30:00Z",
  "score": 82.4,
  "profile_tags": ["kanban", "memory", "web", "skills"],
  "execution_surface": "kanban_delegation",
  "suite_taxonomy": "current",
  "artifact_paths": {
    "run_manifest": "run-manifest.json",
    "score": "score.json",
    "suite_results": "suite-results.json",
    "case_results": "case-results.jsonl",
    "judge_decisions": "judge-decisions.jsonl",
    "profile_snapshot": "profile-snapshot.redacted.yaml",
    "trace": "trace.json"
  },
  "source": {
    "profile_distribution": "https://github.com/acme/hermes-profile",
    "pull_request": null
  },
  "review": {
    "public_transcripts_redacted": true,
    "secrets_removed": true,
    "private_paths_removed": true,
    "manual_review_notes": "No known private data remains."
  }
}
```

## Review Rules

Before opening a pull request, the coding agent must verify:

- required files exist
- run id and score match across artifacts
- public transcript fields are redacted
- profile snapshot is redacted
- no secrets, auth files, raw memories, `.env`, private local paths, or
  unredacted personal data are present
- suite taxonomy is current, or the submission is clearly marked as legacy

## User Prompt

```text
Use the HermesBench skill to publish my latest benchmark result as a public leaderboard submission.

Skill: https://github.com/verkyyi/hermesbench/blob/main/agent-skills/hermesbench/SKILL.md

Follow the skill's "Publish A Benchmark Result" workflow. Prepare the submission artifacts, validate redaction, and open a pull request when ready.
```
