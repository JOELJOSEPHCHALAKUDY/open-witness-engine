# Milestones

## v0 — Tested domain core + bridge foundation (done)

The off-robot decision model, causal graph, provenance store, query surface, and the
non-blocking capture bridge with Open-RMF / Nav2 adapter mappings — built test-first,
with the ROS-specific I/O left as documented seams. Hardened against malformed
records (fail-open). See [CHANGELOG.md](CHANGELOG.md).

## v0.1 — Live ROS 2 capture (done, sim-run pending)

- ✅ Thread-safe (locked) spool for concurrent ROS callback vs. drain, with
  concurrency tests.
- ✅ Live ROS 2 node (`bridge/ros_node.py`) subscribing to Open-RMF task topics and
  feeding the bridge fail-open, behind a guarded `rclpy` import; extraction is tested
  without ROS.
- ⏳ Remaining: confirm the message-field mapping against a live distro and run against
  Open-RMF / Nav2 in a real simulator (needs a ROS 2 environment); wire the Nav2
  behavior-tree topic the same way as RMF.

## v0.2 — Persistence + retrieval (in progress)

- ✅ Persistent `SqliteProvenanceStore` implementing the same `ProvenanceStore`
  contract (Postgres later behind the same interface).
- ✅ Content-hashed references to `rosbag2` / `ros2_tracing` / world-state snapshots.
- ✅ Store-agnostic queries (work over any backend).
- ⏳ Remaining: semantic (embedding) retrieval over decision records.

## Later (gated on a validated customer wedge)

Fleet aggregation across robots and sites; tamper-evident hash-chained audit; SROS2
identity mapping; operator-facing decision-provenance query UI.

> Scope discipline: none of these move OWE onto a robot control/safety path. OWE is
> and remains observation-only and advisory. See [docs/boundaries.md](docs/boundaries.md).
