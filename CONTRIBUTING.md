# Contributing

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
mypy src tests   # strict
```

Python 3.12+.

## Standards

- **Test-first.** No production code without a failing test. Add property-based
  tests for new invariants.
- **Strict typing.** `mypy --strict` and `ruff` must pass; Pydantic v2 for all
  envelopes.
- **Append-only.** Corrections/invalidations are new records linked by causal edges
  (`corrected_by` / `superseded_by` / `invalidated_by`), never in-place mutation.
- **No dependency on `../open-timeline-engine`.** Reimplement primitives here.
- Keep `schemas/*.json` versioned and the Pydantic models in sync with them.

## The safety invariants are non-negotiable

Do not accept a change that puts OWE in a control/safety path, lets it define the
safe action set, makes capture block a robot, or stores raw sensor data. See
[AGENTS.md](AGENTS.md) and [docs/boundaries.md](docs/boundaries.md). If a change
appears to require crossing one of these lines, raise it rather than proceeding.

## Pull requests

- Include tests and docs updates for public interfaces.
- Note any `schemas/` changes and keep them backward-compatible for additive updates.
- Call out anything that touches the capture/transport path or a safety boundary.
