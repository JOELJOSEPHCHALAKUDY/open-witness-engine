# Milestones

## v0 — Tested domain core + bridge foundation (done)

The off-robot decision model, causal graph, provenance store, query surface, and the
non-blocking capture bridge with Open-RMF / Nav2 adapter mappings — built test-first,
with the ROS-specific I/O left as documented seams. Hardened against malformed
records (fail-open). See [CHANGELOG.md](CHANGELOG.md).

## v0.1 — Live ROS 2 capture in simulation (next)

- Wire the RMF and Nav2 adapter seams to live ROS 2 message types
  (`rmf_task_msgs`, Nav2 behavior-tree logging).
- Run the bridge against Open-RMF / Nav2 in simulation, observation-only.
- Add thread-safety (locked spool) for concurrent ROS callback vs. drain, with
  concurrency tests.

## v0.2 — Persistence + retrieval

- Persistent `ProvenanceStore` backend (Postgres) implementing the same protocol.
- Semantic retrieval over decision records; references and content hashes to
  `rosbag2` / `ros2_tracing` snapshots.

## Later (gated on a validated customer wedge)

Fleet aggregation across robots and sites; tamper-evident hash-chained audit; SROS2
identity mapping; operator-facing decision-provenance query UI.

> Scope discipline: none of these move OWE onto a robot control/safety path. OWE is
> and remains observation-only and advisory. See [docs/boundaries.md](docs/boundaries.md).
