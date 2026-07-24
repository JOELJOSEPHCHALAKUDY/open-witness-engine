# Open Witness Engine — v0 design

Date: 2026-07-24
Status: implemented. The domain core shipped as designed; the capture bridge
foundation and malformed-record resilience (originally v0.1) were also built. See
[CHANGELOG.md](../../CHANGELOG.md) and [MILESTONES.md](../../MILESTONES.md) for
current status; this document is the original approved design.

## Purpose

Decision provenance and shared operational memory for robot fleets. Record what a
robot believed, why it chose an action over the alternatives, what happened, and how
a human corrected it — then make that queryable across the fleet. Observation-only,
advisory, off the control loop. See [../boundaries.md](../boundaries.md).

This project was scoped from a feasibility study of whether Open Timeline Engine (TCE)
could serve robotics. Conclusion: TCE is the wrong *stack* to fork (human-workflow
data rates, no real-time/safety story, dev-workflow schema), but its decision-memory
*concept* and event-ordering *primitives* transfer. OWE is a fresh, independent build
that borrows those patterns.

## v0 scope

The off-robot domain core, built test-first. No ROS integration yet.

- `envelope.py` — `RobotDecisionEnvelope v1`: the decision tuple + identity + clocks +
  ordering, as Pydantic v2 models mirroring `schemas/robot-decision-envelope.v1.json`.
- `causal.py` — typed causal edges (`caused_by`, `chosen_over`, `constrained_by`,
  `executed_as`, `resulted_in`, `corrected_by`, `invalidated_by`, `superseded_by`) and
  a `DecisionGraph` with lineage traversal.
- `ordering.py` — `source_seq` / vector-clock / idempotency-key primitives
  reimplemented cleanly from TCE's proven design.
- `store.py` — `ProvenanceStore` protocol + `InMemoryProvenanceStore`: append-only,
  idempotent (duplicate `idempotency_key` is a no-op), per-source monotonic ordering,
  supersession-aware.
- `query.py` — decision-provenance queries: reconstruct the rationale for a decision,
  diff outcomes across software versions, and find similar prior situations and what
  was decided.

## Data flow

```
Producer (future: owe_ros_bridge over Open-RMF/Nav2)
  -> RobotDecisionEnvelope (validated)
  -> ProvenanceStore.append  (idempotent, ordered, append-only)
       -> DecisionGraph edges recorded alongside envelopes
  -> query.py reads the store to answer why / version-diff / similar-situation
```

Factual decision variables and causal edges are persisted first. Human-readable
explanation (an LLM narrating the stored facts with citations) is a later,
*downstream* concern — never the source of truth.

## Design decisions

- **No dependency on TCE.** Primitives are reimplemented here; the domains and quality
  bars diverge, and OWE must stand alone.
- **Append-only + supersession, not mutation.** Corrections and invalidations are new
  records linked by `corrected_by` / `superseded_by` / `invalidated_by`, preserving the
  audit trail (the property a provenance system exists for).
- **In-memory store behind a protocol.** A persistent (Postgres) backend implements the
  same protocol later without touching callers.
- **Strict typing + TDD.** Pydantic validation, `mypy --strict`, tests before code.

## Testing

Each module is developed test-first: ordering primitives (sequence gaps, idempotency,
vector-clock causality), envelope validation (required fields, clock/identity
integrity), causal graph (edge typing, lineage traversal, cycle safety), store
(append-only enforcement, idempotent replay, ordered retrieval, supersession), and
query (rationale reconstruction, version-diff, similar-situation).

## Out of scope for v0 (roadmap)

ROS bridge, persistence, semantic retrieval, fleet aggregation, tamper-evident
hash-chaining, SROS2 identity, operator UI. These are gated on validating a real
customer wedge, per the feasibility study.
