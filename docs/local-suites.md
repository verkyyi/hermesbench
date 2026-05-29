# Local Suites

Local suites let Hermes users evaluate private workflows without forking the
public HermesBench benchmark.

Use local suites for:

- company/team workflows
- private toolchains
- internal gateway platforms
- product-specific regression prompts
- personal assistant workflows that should not be in a public benchmark

Do not use local suites to change the public HermesBench score. Treat them as a
second layer: public score for comparable Hermes harness quality, local score
for your own deployment.

## Loading Local Suites

```bash
hermesbench --suite-path ./my-suites --list-suites
HERMES_RUN_LLM_EVALS=1 hermesbench --suite-path ./my-suites
```

You can also set:

```bash
export HERMESBENCH_SUITE_PATH="./my-suites:/another/suite.json"
```

HermesBench also auto-loads `~/.hermes/hermesbench/suites` when it exists.

## File Format

Local suites can be JSON or YAML. A file contains packages and categories:

```yaml
packages:
  team_ops:
    label: Team ops
    description: Private team workflows.
    categories:
      - team_ops_status

categories:
  - id: team_ops_status
    label: Team ops status
    package: team_ops
    budget:
      reply_target_s: 35
      conclude_s: 150
    cases:
      - id: release_unknown
        expectation: clarify
        prompt: Is the release safe to ship?
        notes: No release evidence is provided; ask what to inspect.
```

## Case Fields

Required:

- `id`: globally unique across bundled and local cases
- `prompt`: user prompt sent to Hermes
- `expectation`: one of `answer`, `task_done`, `clarify`, `refuse`

Recommended:

- `notes`: judge-facing rubric notes
- `category`: optional inside each case; defaults to the category id

## Side Effects

Default prompt suites may use side effects only inside the benchmark workdir.
This makes local suites realistic without risking production state.

Safe:

- create a fixture file in `HERMES_BENCH_WORKDIR`
- edit files created by the benchmark
- summarize a fixture document

Unsafe for default suites:

- send external messages
- modify real user files
- restart production services
- spend money
- change cloud infrastructure

Put unsafe/live workflows behind explicit opt-in runtime suites.

## Design Advice

- Keep local cases short enough for daily runs.
- Prefer harness/config behavior over model IQ puzzles.
- Include ambiguous and refusal cases, not only happy paths.
- Add cases for tool routing, memory hygiene, progress updates, and side-effect
  boundaries.
- Keep prompts generic enough that future you can still understand the failure.
