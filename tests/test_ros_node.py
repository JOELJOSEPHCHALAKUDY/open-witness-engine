"""Live ROS 2 bridge node — the v0.1 seam.

The rclpy wiring only runs on a real ROS 2 system, so the ROS-independent logic
(message -> record extraction, and capture into the bridge) lives in pure
functions tested here with duck-typed fake messages. The node factory itself is
guarded: importing this module never requires ROS, and building the node without
rclpy raises a clear error.
"""

from types import SimpleNamespace

import pytest

from open_witness_engine.bridge.pipeline import Bridge
from open_witness_engine.bridge.ros_node import (
    HAS_RCLPY,
    capture_rmf_task,
    extract_rmf_task,
    make_bridge_node,
)
from open_witness_engine.store import InMemoryProvenanceStore

_ISO = "2026-07-24T09:00:05+00:00"


def _rmf_msg(robot: str = "robot-3", state: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        task_id="delivery-82",
        fleet_name="warehouse-a",
        robot_name=robot,
        state=state,
        description="Deliver container to station B",
        bids=[
            SimpleNamespace(robot_name="robot-3", cost=11.8),
            SimpleNamespace(robot_name="robot-7", cost=14.2),
        ],
    )


def test_extract_rmf_task_produces_a_valid_envelope() -> None:
    rec = extract_rmf_task(_rmf_msg(), wall_time_iso=_ISO, monotonic_ns=5_000_000)
    assert rec is not None
    assert rec["task_id"] == "delivery-82"
    assert rec["awarded_robot"] == "robot-3"
    assert {b["robot"] for b in rec["bids"]} == {"robot-3", "robot-7"}
    assert rec["status"] == "completed"
    # The record round-trips through the tested adapter into a valid envelope.
    from open_witness_engine.bridge.rmf import rmf_task_award_to_observation

    env = rmf_task_award_to_observation(rec).to_envelope(source_seq=0)
    assert env.selected_action == "robot-3"


def test_extract_returns_none_before_an_award() -> None:
    # No robot assigned yet -> not a decision worth recording.
    assert extract_rmf_task(_rmf_msg(robot=""), wall_time_iso=_ISO, monotonic_ns=1) is None


def test_capture_rmf_task_flows_into_the_store() -> None:
    store = InMemoryProvenanceStore()
    bridge = Bridge(store)
    captured = capture_rmf_task(bridge, _rmf_msg(), wall_time_iso=_ISO, monotonic_ns=5_000_000)
    assert captured is True
    report = bridge.drain()
    assert report.accepted == 1
    got = store.get("rmf:delivery-82:award")
    assert got is not None and got.selected_action == "robot-3"


def test_capture_is_fail_open_on_a_bad_message() -> None:
    store = InMemoryProvenanceStore()
    bridge = Bridge(store)
    # Missing task_id -> extraction yields a record the adapter rejects; capture
    # must absorb it (never raise) and count it, not crash the node.
    bad = SimpleNamespace(robot_name="robot-3", state=2, bids=[])
    result = capture_rmf_task(bridge, bad, wall_time_iso=_ISO, monotonic_ns=1)
    assert result is False  # rejected, not raised


def test_module_imports_without_ros_and_factory_guards() -> None:
    assert HAS_RCLPY is False  # ROS is not installed in this environment
    with pytest.raises(RuntimeError):
        make_bridge_node(Bridge(InMemoryProvenanceStore()))
