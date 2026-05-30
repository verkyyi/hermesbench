# HermesBench Alpha Feedback

HermesBench is ready for narrow alpha feedback from Hermes Agent users who can
run a coding agent against their own configuration.

The most useful feedback is concrete and evidence-backed:

- Did the default one-recipe run complete?
- Which setup step was unclear or brittle?
- Did the score match your own read of the agent's answer?
- Which scenario felt unrealistic, too private, or too easy to game?
- What profile/config detail would you need before trusting a leaderboard row?

## Recommended Feedback Run

Start with the default single-recipe path. Full bundle runs are intentionally
opt-in because they take longer and cost more.

```text
Use the HermesBench skill and run one default scenario recipe for my current Hermes configuration.

Skill: https://github.com/verkyyi/hermesbench/blob/main/agent-skills/hermesbench/SKILL.md

Follow the skill's "Run Current Hermes Configuration" workflow. Use the Python API default single-recipe path, save artifacts, and summarize the score and main findings. Do not run the full bundle unless I explicitly ask.
```

## What To Share

Open an issue with:

- HermesBench version or commit SHA.
- Hermes Agent install method and target surface (`cli`, `telegram`, `weixin`,
  or custom command bridge).
- The scenario id, run id, overall score, and axis scores.
- The first setup error or confusing instruction, if any.
- Redacted public artifacts only. Do not attach raw transcripts, auth files,
  `.env` files, raw memories, or private local paths.

For leaderboard submissions, use the contract in
[`data/submissions/README.md`](data/submissions/README.md). For recipe ideas,
describe the real user job, why it matters, and what evidence would prove the
agent handled it correctly.
