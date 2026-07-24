# Changelog

## Unreleased

- **Fail-open hardening (found by a 5,000-sample stress eval):** `Bridge.capture`
  and `drain` now absorb the full set of malformed-record failures — not just
  `MalformedRecordError` but also `ValidationError`, `ValueError`, `TypeError`, and
  `DuplicateDecisionError`. A malformed numeric field (`monotonic_ns="abc"` →
  `ValueError` from `int()`, or a negative value → Pydantic `ValidationError`) used
  to escape capture and would have crashed a ROS callback; it is now rejected and
  counted. Regression tests in `tests/test_fail_open_numeric.py`.

## 0.1.0

v0.1 + partial v0.2: the pipeline now runs end-to-end (persistently) and has a live
ROS 2 seam. Still observation-only, advisory, off the control loop.

### v0.1 — concurrency + live ROS

- **Thread-safe spool**: `BoundedSpool` now guards `offer`/`drain` with a lock, so a
  ROS callback (producer) and the bridge drain (consumer) are safe on separate
  threads and under free-threaded Python. Conservation + no-duplicate invariants are
  tested under concurrent load.
- **Live ROS 2 node** (`bridge/ros_node.py`): subscribes to Open-RMF task topics and
  feeds the `Bridge` fail-open, draining into the store on a timer. The `rclpy`/message
  imports are behind a guarded import so the module stays importable and tested without
  ROS; the message-field mapping is a documented seam to confirm on a live distro.

### v0.2 (partial) — persistence + references

- **`SqliteProvenanceStore`**: durable, append-only, idempotent, ordered, causal-edge
  and supersession-aware — the same contract as the in-memory store, surviving restart.
  Postgres can drop in later behind the same interface.
- **Content-hashed references** (`references.py`): `content_hash`, `snapshot_ref`, and
  `verify_ref` let OWE store verifiable, tamper-evident references to rosbag2 / trace /
  world-state snapshots without holding the raw data.
- **Store-agnostic queries**: `explain_decision` / `outcome_rates_by_version` /
  `similar_prior_decisions` now accept any `ProvenanceStore` (in-memory or SQLite).

### Tooling & docs

- **CI** (`.github/workflows/ci.yml`): ruff + mypy `--strict` + pytest on every push/PR.
- **`examples/warehouse_demo.py`**: a runnable, no-ROS minimal working example that
  drives the full capture → persist → query path.
- **Validated on real ROS 2 (Jazzy)**: `examples/ros2_integration.py` +
  `docker/ros-test.Dockerfile` run OWE's capture path through a live `rclpy` executor
  over real DDS — two tasks published, both captured and correctly explained. See
  [docs/ros2-testing.md](docs/ros2-testing.md). (Uses `std_msgs/String` as a stand-in
  for `rmf_task_msgs/TaskSummary`; full Open-RMF/Gazebo sim still pending.)

Validation: 99 tests passing; `ruff check .` clean; `mypy --strict` clean (32 files).

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
