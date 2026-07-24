# Changelog

## 0.0.1

Initial release: the tested off-robot domain core and the non-blocking capture
bridge foundation. Observation-only, advisory, off the control loop (see
[docs/boundaries.md](docs/boundaries.md)).

### Domain core

- `RobotDecisionEnvelope v1` — the decision tuple (world-state ref, goal, candidate
  actions, constraints, software versions, selected action, outcome, human override)
  with identity, monotonic + wall clocks, and per-source ordering. Mirrors
  `schemas/robot-decision-envelope.v1.json`.
- Typed causal graph — `caused_by`, `chosen_over`, `constrained_by`, `executed_as`,
  `resulted_in`, `corrected_by`, `invalidated_by`, `superseded_by`; cycle-safe
  lineage traversal and version-tip resolution.
- Ordering primitives — `source_seq` / vector clock / idempotency, reimplemented
  cleanly (no dependency on Open Timeline Engine).
- Append-only provenance store — idempotent replay, per-source ordering, gap
  detection, supersession without mutation.
- Query surface — `explain_decision`, `outcome_rates_by_version` (localize a software
  regression), `similar_prior_decisions`.

### Capture bridge (`owe_ros_bridge`)

- Non-blocking bounded spool: `offer()` never blocks or raises; drops oldest on
  overflow and counts it. The fail-open transport.
- `DecisionObservation` + envelope translation; identity derives from the source
  event id so replays deduplicate.
- Open-RMF task-award and Nav2 behavior-tree adapter mappings (ROS I/O left as
  documented seams).
- `Bridge` facade — the fail-open front door: `capture(adapter, record)` never
  raises (malformed record is counted and dropped), `drain()` absorbs per-record
  validation failures. Loss is bounded and observable via `bridge.rejected` /
  `bridge.dropped`.
- `MalformedRecordError` with context, so a bad record is rejectable rather than
  crash-inducing.

### Testing

- Example-based unit tests across every module.
- Property-based tests (Hypothesis, ~8,800 generated scenarios) on the load-bearing
  invariants: spool conservation, vector-clock strict partial order, cycle-safe
  graph traversal, envelope round-trip, store dedup/ordering.
- At-scale volume tests (10k–100k): sustained spool overflow, 20k decisions across
  50 robots, deep supersession/causal chains, exact gap detection.
- Resilience tests: malformed records never crash the bridge.

Validation for this release: 80 tests passing; `ruff check .` clean; `mypy --strict`
clean (25 files).

### Not included (roadmap — see README)

Live ROS 2 wiring, thread-safety for concurrent callback/drain, persistence,
semantic retrieval, fleet aggregation, tamper-evident hash-chaining.
