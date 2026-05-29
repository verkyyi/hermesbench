# Profile Distribution Baselines

HermesBench is most useful when benchmark results are tied to the Hermes runtime
configuration that produced them.

For public sharing, prefer the Hermes **profile distribution** model described
in the Hermes Agent docs:
https://hermes-agent.nousresearch.com/docs/user-guide/profile-distributions

- A profile distribution is a git repository for a whole agent: `distribution.yaml`,
  `SOUL.md`, `config.yaml`, bundled skills, cron jobs, and MCP connections.
- Installers use `hermes profile install <repo> --alias`.
- Credentials, `.env`, memories, sessions, state databases, logs, workspaces,
  caches, and local customizations are user-owned and are not distributed.

That maps directly to HermesBench:

1. Publish or link the profile distribution repo.
2. Run HermesBench against that installed profile.
3. Publish the score JSON, profile fingerprint, command, runtime, and suite
   scores.
4. Redact anything user-owned.

## Baseline Types

### Installable Distribution Baseline

Best for public agents intended for reuse.

Required:

- distribution repo URL
- distribution version or commit SHA
- HermesBench version or commit SHA
- run command
- score JSON

### Redacted Distribution-Style Baseline

Best when a local profile should be used as a public comparison point but cannot
be installed by others.

Required:

- model/provider
- memory provider and whether memory is enabled
- toolsets
- public plugin names
- benchmark env vars
- profile hash
- explicit list of redactions

The first checked-in baseline, `data/baselines/verkyyi-default-2026-05-29`, uses
this second form.

## What Not To Publish

Never publish:

- API keys or auth files
- `.env`
- memories or sessions
- logs or state databases
- raw private chats
- local filesystem paths
- personal account identifiers

## Submission Checklist

- The result includes `score.json`.
- The runtime configuration is either linked as a profile distribution repo or
  summarized as a redacted distribution-style baseline.
- The exact command and benchmark version are recorded.
- The result says whether high-rate mode was used.
- The result says which suites were skipped.
- Side effects are scoped and auditable.
