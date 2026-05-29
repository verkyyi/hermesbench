# Contributing

HermesBench is scoped to Hermes Agent runtime-configuration evaluation.

Good public benchmark cases:

- target Hermes users
- measure harness/config behavior, not base-model contest ability
- are privacy-safe and generic
- finish quickly enough for daily runs
- have clear expected handling
- avoid real external side effects

Public bundled categories should remain balanced. Local suites can be uneven
because they serve private regression needs.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m hermesbench --validate
```

## Pull Requests

Include:

- why the change belongs in HermesBench
- what user or harness behavior it measures
- how it was verified
- whether it affects the public score surface
