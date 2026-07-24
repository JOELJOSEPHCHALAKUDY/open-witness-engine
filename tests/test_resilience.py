"""Resilience: a malformed record must never crash the bridge.

Found by driving the engine by hand — the adapters raised raw KeyError/ValueError
on missing fields and bad timestamps, which in the drain loop would stall capture
and break the fail-open guarantee. Adapters now raise a typed, contextual
MalformedRecordError, and the Bridge facade skips-and-counts bad records.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from open_witness_engine.bridge.errors import MalformedRecordError
from open_witness_engine.bridge.nav2 import nav2_bt_to_observation
from open_witness_engine.bridge.pipeline import Bridge
from open_witness_engine.bridge.rmf import rmf_task_award_to_observation
from open_witness_engine.store import InMemoryProvenanceStore

_T0 = datetime(2026, 7, 24, 9, 0, tzinfo=UTC).isoformat()


def _good_rmf(task_id: str = "t1") -> dict[str, Any]:
    return {
        "task_id": task_id,
        "wall_time": _T0,
        "monotonic_ns": 1,
        "goal": "Deliver container",
        "bids": [{"robot": "robot-3", "cost": 1.0}],
        "awarded_robot": "robot-3",
        "status": "succeeded",
    }


def test_missing_field_raises_typed_error_with_context() -> None:
    record = _good_rmf()
    del record["goal"]
    with pytest.raises(MalformedRecordError) as exc:
        rmf_task_award_to_observation(record)
    assert exc.value.source == "rmf-bridge"
    assert "goal" in str(exc.value)


def test_bad_timestamp_raises_typed_error() -> None:
    record = _good_rmf()
    record["wall_time"] = "yesterday afternoon"
    with pytest.raises(MalformedRecordError) as exc:
        rmf_task_award_to_observation(record)
    assert "wall_time" in str(exc.value)


def test_nav2_missing_field_raises_typed_error() -> None:
    with pytest.raises(MalformedRecordError):
        nav2_bt_to_observation({"robot": "r1"})  # missing everything else


def test_unknown_status_is_still_graceful_not_an_error() -> None:
    record = _good_rmf()
    record["status"] = "exploded"
    obs = rmf_task_award_to_observation(record)  # must not raise
    assert obs.outcome.status.value == "in_progress"


def test_bridge_survives_a_mix_of_good_and_malformed_records() -> None:
    store = InMemoryProvenanceStore()
    bridge = Bridge(store)

    bad_missing = _good_rmf("bad-1")
    del bad_missing["goal"]
    bad_ts = _good_rmf("bad-2")
    bad_ts["wall_time"] = "not-a-time"

    # Adapter-time failures (bad records) are absorbed, not raised.
    assert bridge.capture(rmf_task_award_to_observation, _good_rmf("ok-1")) is True
    assert bridge.capture(rmf_task_award_to_observation, bad_missing) is False
    assert bridge.capture(rmf_task_award_to_observation, bad_ts) is False
    assert bridge.capture(rmf_task_award_to_observation, _good_rmf("ok-2")) is True

    report = bridge.drain()
    assert report.accepted == 2
    assert report.rejected == 2
    assert {e.task_id for e in store.all()} == {"ok-1", "ok-2"}


def test_bridge_absorbs_a_drain_time_validation_failure() -> None:
    store = InMemoryProvenanceStore()
    bridge = Bridge(store)
    # Chosen route not among considered -> passes the adapter, fails envelope
    # validation at drain time. The drain loop must survive it.
    bad = {
        "robot": "r1",
        "nav_goal_id": "n1",
        "wall_time": _T0,
        "monotonic_ns": 1,
        "goal": "g",
        "considered": ["route-west"],
        "chosen": "route-teleport",
        "result": "succeeded",
    }
    bridge.capture(nav2_bt_to_observation, bad)
    bridge.capture(
        rmf_task_award_to_observation, _good_rmf("ok")
    )
    report = bridge.drain()
    assert report.accepted == 1
    assert report.rejected == 1
    assert [e.task_id for e in store.all()] == ["ok"]


def test_bridge_assigns_sequential_source_seq_per_source() -> None:
    store = InMemoryProvenanceStore()
    bridge = Bridge(store)
    for i in range(3):
        bridge.capture(rmf_task_award_to_observation, _good_rmf(f"t{i}"))
    bridge.drain()
    seqs = [e.source_seq for e in store.by_source("robot-3")]
    assert seqs == [0, 1, 2]
