"""Fail-open must hold for malformed *numeric* fields too.

A 5,000-sample stress run found that a bad ``monotonic_ns`` escaped capture: a
non-numeric value raises ValueError from ``int()`` and a negative value raises a
Pydantic ValidationError, neither of which the Bridge caught. On a robot that
would crash the ROS callback. Capture must absorb any malformed record, however
it fails.
"""

from typing import Any

from open_witness_engine.bridge.pipeline import Bridge
from open_witness_engine.bridge.rmf import rmf_task_award_to_observation
from open_witness_engine.store import InMemoryProvenanceStore

_ISO = "2026-07-24T09:00:00+00:00"


def _rec(**over: Any) -> dict[str, Any]:
    rec = {
        "task_id": "t1", "fleet": "wh", "wall_time": _ISO, "monotonic_ns": 1,
        "goal": "g", "bids": [{"robot": "r1", "cost": 1.0}],
        "awarded_robot": "r1", "status": "completed",
    }
    rec.update(over)
    return rec


def _capture(rec: dict[str, Any]) -> bool:
    bridge = Bridge(InMemoryProvenanceStore())
    return bridge.capture(rmf_task_award_to_observation, rec)  # must never raise


def test_non_numeric_monotonic_is_rejected_not_raised() -> None:
    assert _capture(_rec(monotonic_ns="abc")) is False


def test_negative_monotonic_is_rejected_not_raised() -> None:
    assert _capture(_rec(monotonic_ns=-5)) is False


def test_none_monotonic_is_rejected_not_raised() -> None:
    assert _capture(_rec(monotonic_ns=None)) is False


def test_wrong_type_bids_is_rejected_not_raised() -> None:
    assert _capture(_rec(bids="not-a-list")) is False


def test_valid_record_still_accepted() -> None:
    assert _capture(_rec()) is True


def test_bridge_survives_a_burst_of_malformed_numeric_records() -> None:
    store = InMemoryProvenanceStore()
    bridge = Bridge(store)
    for i in range(200):
        bridge.capture(rmf_task_award_to_observation, _rec(task_id=f"bad-{i}", monotonic_ns="xyz"))
        bridge.capture(rmf_task_award_to_observation, _rec(task_id=f"ok-{i}"))
    report = bridge.drain()
    assert report.rejected == 200
    assert report.accepted == 200
    assert len(list(store.all())) == 200
