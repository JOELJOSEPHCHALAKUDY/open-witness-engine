"""SQLite-backed provenance store (v0.2 persistence).

Must behave exactly like the in-memory store — append-only, idempotent, ordered,
gap-detecting, supersession-aware — but survive a process restart. It implements
the same ProvenanceStore contract, so callers do not change; Postgres can later
drop in behind the same interface.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from open_witness_engine.causal import CausalEdgeType
from open_witness_engine.envelope import (
    CandidateAction,
    Outcome,
    OutcomeStatus,
    RobotDecisionEnvelope,
)
from open_witness_engine.sqlite_store import SqliteProvenanceStore
from open_witness_engine.store import DuplicateDecisionError

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


def test_append_and_get(tmp_path: Path) -> None:
    store = SqliteProvenanceStore(tmp_path / "owe.db")
    store.append(_env(0, "d-0"))
    got = store.get("d-0")
    assert got is not None and got.decision_id == "d-0"
    assert got.selected_action == "route-west"


def test_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "owe.db"
    store = SqliteProvenanceStore(path)
    store.append(_env(0, "d-0"))
    store.append(_env(1, "d-1"))
    store.close()

    reopened = SqliteProvenanceStore(path)
    assert [e.decision_id for e in reopened.all()] == ["d-0", "d-1"]
    got = reopened.get("d-1")
    assert got is not None and got.source_seq == 1


def test_idempotent_replay(tmp_path: Path) -> None:
    store = SqliteProvenanceStore(tmp_path / "owe.db")
    store.append(_env(0, "d-0", key="robot-3:0"))
    store.append(_env(0, "d-0", key="robot-3:0"))  # duplicate no-op
    assert len(list(store.all())) == 1


def test_reusing_key_for_different_decision_raises(tmp_path: Path) -> None:
    store = SqliteProvenanceStore(tmp_path / "owe.db")
    store.append(_env(0, "d-0", key="robot-3:0"))
    with pytest.raises(DuplicateDecisionError):
        store.append(_env(1, "d-OTHER", key="robot-3:0"))


def test_ordered_by_source_and_gap_detection(tmp_path: Path) -> None:
    store = SqliteProvenanceStore(tmp_path / "owe.db")
    store.append(_env(2, "d-2"))
    store.append(_env(0, "d-0"))
    assert [e.decision_id for e in store.by_source("robot-3")] == ["d-0", "d-2"]
    assert store.missing_sequence("robot-3") == [1]


def test_supersession_and_causal_edges_persist(tmp_path: Path) -> None:
    path = tmp_path / "owe.db"
    store = SqliteProvenanceStore(path)
    store.append(_env(0, "d-0"))
    store.append(_env(1, "d-1"))
    store.link("d-1", CausalEdgeType.CAUSED_BY, "d-0")
    store.supersede(old="d-0", new="d-1")
    store.close()

    reopened = SqliteProvenanceStore(path)
    assert reopened.current_version("d-0") == "d-1"
    edges = reopened.edges_from("d-1", CausalEdgeType.CAUSED_BY)
    assert [e.dst for e in edges] == ["d-0"]
    # original still present and unchanged (append-only)
    assert reopened.get("d-0") is not None
