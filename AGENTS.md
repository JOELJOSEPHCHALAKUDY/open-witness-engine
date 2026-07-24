# Open Witness Engine — agent guide

Decision provenance and shared operational memory for robot fleets. Read
[README.md](README.md) and [docs/boundaries.md](docs/boundaries.md) before changing code.

## Non-negotiable invariants

These are architectural, not preferences. Do not weaken them, and reject any task that
would:

1. Put OWE in a control, perception, emergency-stop, SLAM, or teleop-assist path.
2. Let OWE define the *safe action set* or execute an action directly. OWE proposes;
   a separate trusted deterministic gateway decides and executes.
3. Make capture block a robot process, or make OWE a system of record on the critical
   path. Ingestion is bounded-queue and fail-open.
4. Store raw sensor data (images, point clouds, high-rate channels). Store compact
   decision records, causal links, hashes, and references only.

If a change appears to require crossing one of these lines, stop and raise it with the
user rather than proceeding.

## Working rules

- **TDD.** No production code without a failing test first. Tests live in `tests/`.
- **Strict typing.** `mypy --strict` must pass; Pydantic v2 models for all envelopes.
- **Append-only.** Corrections/invalidations are new records linked by causal edges
  (`corrected_by` / `superseded_by` / `invalidated_by`) — never in-place mutation.
- **No dependency on `../open-timeline-engine`.** Reimplement primitives here; do not
  import from that project.

## Commands

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy src tests
```
