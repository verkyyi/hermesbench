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

## Multi-Profile / Worker Baselines

If a HermesBench result exercises kanban delegation, origin return, or any
multi-worker execution path, the baseline must publish every profile involved in
that measured path:

- front-desk/default profile
- orchestrator profile
- each worker profile that can receive work
- any routing/delegation profile used by the suite

Publishing can happen in either form:

- preferred: link each profile as an installable Hermes profile distribution
  repository
- acceptable for private/local profiles: include a redacted distribution-style
  snapshot for each profile

If kanban is merely enabled in config but no delegated/multi-worker suite ran,
the baseline should say that explicitly and list worker profiles as "present but
not exercised" rather than implying they contributed to the score.

## Submission Checklist

- The result includes `score.json`.
- The runtime configuration is either linked as a profile distribution repo or
  summarized as a redacted distribution-style baseline.
- Any worker profiles involved in measured delegated execution are published or
  redacted individually.
- The exact command and benchmark version are recorded.
- The result says whether high-rate mode was used.
- The result says which suites were skipped.
- Side effects are scoped and auditable.
