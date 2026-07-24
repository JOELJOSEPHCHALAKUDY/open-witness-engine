"""Append-only provenance store.

Off-robot, non-authoritative system of record for decisions. Append-only:
corrections and invalidations are new records linked by causal edges, never
in-place mutation — preserving the audit trail a provenance system exists for.

``InMemoryProvenanceStore`` is the reference implementation behind the
``ProvenanceStore`` protocol; a persistent (Postgres) backend implements the
same protocol later without touching callers.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol, runtime_checkable

from .causal import CausalEdge, CausalEdgeType, DecisionGraph
from .envelope import RobotDecisionEnvelope
from .ordering import IdempotencyLedger, SequenceTracker


class DuplicateDecisionError(Exception):
    """Raised when an idempotency key is reused for a different decision."""


@runtime_checkable
class ProvenanceStore(Protocol):
    def append(self, envelope: RobotDecisionEnvelope) -> None: ...
    def get(self, decision_id: str) -> RobotDecisionEnvelope | None: ...
    def all(self) -> Iterable[RobotDecisionEnvelope]: ...
    def by_source(self, source_id: str) -> list[RobotDecisionEnvelope]: ...


class InMemoryProvenanceStore:
    """Reference append-only store with ordering, idempotency, and a causal graph."""

    def __init__(self) -> None:
        self._by_id: dict[str, RobotDecisionEnvelope] = {}
        self._append_order: list[str] = []
        self._by_source: dict[str, list[str]] = {}
        self._idempotency = IdempotencyLedger()
        self._key_to_decision: dict[str, str] = {}
        self._sequence = SequenceTracker()
        self.graph = DecisionGraph()

    def append(self, envelope: RobotDecisionEnvelope) -> None:
        key = envelope.idempotency_key
        if self._idempotency.seen(key):
            existing = self._key_to_decision.get(key)
            if existing != envelope.decision_id:
                raise DuplicateDecisionError(
                    f"idempotency_key {key!r} already used for decision {existing!r}"
                )
            return  # true duplicate replay — no-op
        self._idempotency.record(key)
        self._key_to_decision[key] = envelope.decision_id
        self._by_id[envelope.decision_id] = envelope
        self._append_order.append(envelope.decision_id)
        self._by_source.setdefault(envelope.source_id, []).append(envelope.decision_id)
        self._sequence.observe(envelope.source_id, envelope.source_seq)

    def get(self, decision_id: str) -> RobotDecisionEnvelope | None:
        return self._by_id.get(decision_id)

    def all(self) -> Iterator[RobotDecisionEnvelope]:
        for decision_id in self._append_order:
            yield self._by_id[decision_id]

    def by_source(self, source_id: str) -> list[RobotDecisionEnvelope]:
        envelopes = [self._by_id[i] for i in self._by_source.get(source_id, [])]
        return sorted(envelopes, key=lambda e: e.source_seq)

    def missing_sequence(self, source_id: str) -> list[int]:
        """Sequence numbers missing between the first and highest seen for a source."""
        seqs = sorted(e.source_seq for e in self.by_source(source_id))
        if not seqs:
            return []
        return [s for s in range(seqs[0], seqs[-1]) if s not in set(seqs)]

    # --- causal graph convenience ---

    def link(self, src: str, edge_type: CausalEdgeType, dst: str) -> CausalEdge:
        return self.graph.link(src, edge_type, dst)

    def supersede(self, *, old: str, new: str) -> CausalEdge:
        """Record that ``new`` supersedes ``old`` (a correction), append-only."""
        return self.graph.link(old, CausalEdgeType.SUPERSEDED_BY, new)

    def current_version(self, decision_id: str) -> str:
        return self.graph.current_version(decision_id)
