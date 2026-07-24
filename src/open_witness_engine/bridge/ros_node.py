"""Live ROS 2 capture node (v0.1).

Subscribes to Open-RMF task and Nav2 topics on a real robot, maps each message
into a decision record, and feeds it — fail-open — into an OWE ``Bridge``, with a
timer draining the bounded spool into the provenance store.

Only the ROS wiring needs rclpy; the message->record extraction is pure and
tested without ROS. Importing this module never requires a ROS install.

NOTE (seam to confirm on a live system): the exact field names below track the
common shapes of ``rmf_task_msgs`` / Nav2 messages but MUST be reconciled with
the message definitions on your distro before production use.
"""

from __future__ import annotations

from typing import Any

from .pipeline import Bridge
from .rmf import rmf_task_award_to_observation

try:  # pragma: no cover - exercised only on a ROS 2 system
    import rclpy  # noqa: F401

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


# RMF TaskSummary.state enum -> the status vocabulary the RMF adapter understands.
_RMF_STATE = {0: "queued", 1: "executing", 2: "completed", 3: "failed", 4: "canceled"}


def _rmf_status(state: Any) -> str:
    if isinstance(state, int):
        return _RMF_STATE.get(state, "executing")
    return str(state).strip().lower() if state is not None else "executing"


def extract_rmf_task(msg: Any, *, wall_time_iso: str, monotonic_ns: int) -> dict[str, Any] | None:
    """Map an RMF task-summary message into a decision record, or None.

    Returns None before a robot has been awarded the task (no decision to record
    yet). The node supplies wall_time / monotonic_ns from its ROS clock.
    """
    awarded = getattr(msg, "robot_name", None)
    if not awarded:
        return None
    bids_raw = getattr(msg, "bids", None) or []
    bids = [
        {"robot": getattr(b, "robot_name", ""), "cost": getattr(b, "cost", None)}
        for b in bids_raw
    ] or [{"robot": awarded, "cost": None}]
    task_id = getattr(msg, "task_id", None)
    return {
        "task_id": task_id,
        "fleet": getattr(msg, "fleet_name", None),
        "wall_time": wall_time_iso,
        "monotonic_ns": monotonic_ns,
        "goal": getattr(msg, "description", None) or f"RMF task {task_id}",
        "bids": bids,
        "awarded_robot": awarded,
        "status": _rmf_status(getattr(msg, "state", None)),
    }


def capture_rmf_task(
    bridge: Bridge, msg: Any, *, wall_time_iso: str, monotonic_ns: int
) -> bool:
    """Extract and capture an RMF task decision. Never raises (fail-open).

    Returns True if a decision was captured, False if the message carried no
    decision or was malformed (the Bridge counts the rejection).
    """
    record = extract_rmf_task(msg, wall_time_iso=wall_time_iso, monotonic_ns=monotonic_ns)
    if record is None:
        return False
    return bridge.capture(rmf_task_award_to_observation, record)


def make_bridge_node(bridge: Bridge, *, drain_period_s: float = 0.5) -> Any:
    """Create the rclpy node that wires RMF/Nav2 subscriptions to ``bridge``.

    Raises RuntimeError if rclpy is unavailable. The node is composed (not
    subclassed) so this module stays importable and testable without ROS.
    """
    if not HAS_RCLPY:
        raise RuntimeError(
            "rclpy is not available; install ROS 2 to run the live witness bridge"
        )
    import rclpy  # local import: only on a ROS 2 system
    from rmf_task_msgs.msg import TaskSummary

    node = rclpy.create_node("owe_witness_bridge")

    def _clock_now() -> tuple[str, int]:
        now = node.get_clock().now()
        ns = int(now.nanoseconds)
        # ROS time is unix-epoch nanoseconds; format an ISO wall time from it.
        from datetime import UTC, datetime

        iso = datetime.fromtimestamp(ns / 1e9, tz=UTC).isoformat()
        return iso, ns

    def _on_task(msg: Any) -> None:
        iso, ns = _clock_now()
        capture_rmf_task(bridge, msg, wall_time_iso=iso, monotonic_ns=ns)

    node.create_subscription(TaskSummary, "/task_summaries", _on_task, 10)
    node.create_timer(drain_period_s, bridge.drain)
    return node


def main() -> None:  # pragma: no cover - runs only on a ROS 2 system
    if not HAS_RCLPY:
        raise SystemExit("rclpy not available; this entrypoint requires ROS 2")
    import rclpy

    from ..store import InMemoryProvenanceStore

    rclpy.init()
    bridge = Bridge(InMemoryProvenanceStore())
    node = make_bridge_node(bridge)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
