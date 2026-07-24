"""Append-only provenance store.

The store is the system of record for decisions (off-robot, non-authoritative).
It must be append-only, idempotent on replay, ordered per source, and it must
carry causal edges alongside envelopes — including corrections that supersede a
prior decision without mutating it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from open_witness_engine.causal import CausalEdgeType
from open_witness_engine.envelope import (
    CandidateAction,
    Outcome,
    OutcomeStatus,
    RobotDecisionEnvelope,
)
from open_witness_engine.store import DuplicateDecisionError, InMemoryProvenanceStore

_T0 = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _env(
    seq: int, decision_id: str, *, robot: str = "robot-3", key: str | None = None
) -> RobotDecisionEnvelope:
    return RobotDecisionEnvelope(
        decision_id=decision_id,
        robot_id=robot,
        wall_time=_T0 + timedelta(seconds=seq),
        monotonic_ns=1_000 * (seq + 1),
        source_seq=seq,
        idempotency_key=key or f"{robot}:{seq}",
        goal="Deliver container to station B",
        candidate_actions=[CandidateAction(action="route-west", cost=14.2)],
        selected_action="route-west",
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED),
    )


def test_append_and_get() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0"))
    got = store.get("d-0")
    assert got is not None
    assert got.decision_id == "d-0"


def test_append_is_idempotent_on_duplicate_key() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0", key="robot-3:0"))
    # Same idempotency key (a retried delivery) is a no-op, not an error.
    store.append(_env(0, "d-0", key="robot-3:0"))
    assert len(list(store.all())) == 1


def test_reusing_a_key_for_a_different_decision_raises() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0", key="robot-3:0"))
    with pytest.raises(DuplicateDecisionError):
        store.append(_env(1, "d-DIFFERENT", key="robot-3:0"))


def test_records_are_not_mutable_through_the_store() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0"))
    first = store.get("d-0")
    assert first is not None
    with pytest.raises(ValidationError):
        first.selected_action = "route-east"


def test_ordered_by_source_returns_source_order() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(2, "d-2"))
    store.append(_env(0, "d-0"))
    store.append(_env(1, "d-1"))
    ordered = store.by_source("robot-3")
    assert [e.decision_id for e in ordered] == ["d-0", "d-1", "d-2"]


def test_gap_detection_across_appended_sequence() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0"))
    store.append(_env(3, "d-3"))
    assert store.missing_sequence("robot-3") == [1, 2]


def test_correction_supersedes_without_mutating_original() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0"))
    store.append(_env(1, "d-1"))
    store.supersede(old="d-0", new="d-1")
    assert store.current_version("d-0") == "d-1"
    # Original still present and unchanged.
    original = store.get("d-0")
    assert original is not None
    assert original.decision_id == "d-0"


def test_link_and_read_causal_edges() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0"))
    store.append(_env(1, "d-1"))
    store.link("d-1", CausalEdgeType.CAUSED_BY, "d-0")
    edges = store.graph.edges_from("d-1", CausalEdgeType.CAUSED_BY)
    assert [e.dst for e in edges] == ["d-0"]


def test_get_missing_returns_none() -> None:
    store = InMemoryProvenanceStore()
    assert store.get("ghost") is None
