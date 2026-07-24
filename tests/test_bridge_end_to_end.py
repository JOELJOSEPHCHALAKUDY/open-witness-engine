"""End-to-end: RMF/Nav2 record -> spool -> envelope -> provenance store -> query.

Proves the seams line up: a source record flows through the non-blocking spool,
translates to a validated envelope with a bridge-assigned sequence, lands in the
append-only store, and is answerable by a provenance query — with replays
deduplicated.
"""

from datetime import UTC, datetime
from typing import Any

from open_witness_engine.bridge.capture import DecisionObservation
from open_witness_engine.bridge.rmf import rmf_task_award_to_observation
from open_witness_engine.bridge.spool import BoundedSpool
from open_witness_engine.query import explain_decision
from open_witness_engine.store import InMemoryProvenanceStore

_T0 = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _record(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "fleet": "warehouse-a",
        "wall_time": _T0.isoformat(),
        "monotonic_ns": 111,
        "goal": "Deliver container to station B",
        "reason": "lowest bid",
        "bids": [
            {"robot": "robot-3", "cost": 11.8},
            {"robot": "robot-7", "cost": 14.2, "rejected_reasons": ["busy"]},
        ],
        "awarded_robot": "robot-3",
        "status": "succeeded",
    }


def test_record_flows_through_spool_into_store_and_is_queryable() -> None:
    store = InMemoryProvenanceStore()
    spool: BoundedSpool[DecisionObservation] = BoundedSpool(capacity=64)

    # Producer side (would be a ROS callback): non-blocking offer.
    spool.offer(rmf_task_award_to_observation(_record("delivery-82")))

    # Consumer side (bridge drain): assign per-source sequence, append.
    seq = 0
    for obs in spool.drain():
        store.append(obs.to_envelope(source_seq=seq))
        seq += 1

    ex = explain_decision(store, "rmf:delivery-82:award")
    assert ex is not None
    assert ex["selected_action"] == "robot-3"
    assert ex["reason"] == "lowest bid"
    assert ex["rejected"] == [{"action": "robot-7", "reasons": ["busy"]}]


def test_replayed_record_is_deduplicated_by_the_store() -> None:
    store = InMemoryProvenanceStore()
    obs = rmf_task_award_to_observation(_record("delivery-82"))
    store.append(obs.to_envelope(source_seq=0))
    # Same source event re-delivered (e.g. a retried bridge) is a no-op.
    store.append(obs.to_envelope(source_seq=1))
    assert len(list(store.all())) == 1
