"""Real ROS 2 integration check for Open Witness Engine.

Runs inside a ROS 2 container (see docs/ros2-testing.md). A real rclpy node
publishes task-summary messages on a real DDS topic; the subscriber drives OWE's
*actual* ``capture_rmf_task`` on the ROS callback, drains on a ROS timer, and we
query the resulting provenance store.

This exercises the live path — real rclpy executor, real DDS transport, real
timers — end to end through OWE's production capture code. ``std_msgs/String``
carries the JSON payload as a stand-in for ``rmf_task_msgs/TaskSummary`` (the only
piece not installed in a plain ROS base image); the field mapping to the real
message type remains the documented seam in ``bridge/ros_node.py``.

    Exit code 0 = PASS.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from open_witness_engine.bridge.pipeline import Bridge
from open_witness_engine.bridge.ros_node import capture_rmf_task
from open_witness_engine.query import explain_decision
from open_witness_engine.store import InMemoryProvenanceStore

TASKS = [
    {
        "task_id": "delivery-82", "fleet_name": "warehouse-a", "robot_name": "robot-3",
        "state": 2, "description": "Deliver container to station B",
        "bids": [{"robot_name": "robot-3", "cost": 11.8},
                 {"robot_name": "robot-7", "cost": 14.2}],
    },
    {
        "task_id": "delivery-83", "fleet_name": "warehouse-a", "robot_name": "robot-7",
        "state": 3, "description": "Deliver to dock 4",
        "bids": [{"robot_name": "robot-7", "cost": 9.0}],
    },
]


def _to_msg_obj(d: dict) -> SimpleNamespace:
    d = dict(d)
    d["bids"] = [SimpleNamespace(**b) for b in d.get("bids", [])]
    return SimpleNamespace(**d)


class WitnessNode(Node):
    def __init__(self, bridge: Bridge) -> None:
        super().__init__("owe_witness_it")
        self.bridge = bridge
        self.create_subscription(String, "task_summaries", self._on_task, 10)
        self._pub = self.create_publisher(String, "task_summaries", 10)
        self.create_timer(0.2, self.bridge.drain)
        self._i = 0
        self.create_timer(0.3, self._publish_next)

    def _publish_next(self) -> None:
        if self._i < len(TASKS):
            self._pub.publish(String(data=json.dumps(TASKS[self._i])))
            self.get_logger().info(f"published {TASKS[self._i]['task_id']}")
            self._i += 1

    def _on_task(self, msg: String) -> None:
        now = datetime.now(tz=UTC)
        capture_rmf_task(
            self.bridge, _to_msg_obj(json.loads(msg.data)),
            wall_time_iso=now.isoformat(), monotonic_ns=time.monotonic_ns(),
        )


def main() -> int:
    rclpy.init()
    store = InMemoryProvenanceStore()
    bridge = Bridge(store)
    node = WitnessNode(bridge)
    deadline = time.time() + 4.0
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    bridge.drain()
    node.destroy_node()
    rclpy.shutdown()

    decisions = list(store.all())
    print("\n=== OWE x ROS 2 integration ===")
    print(f"published {len(TASKS)} tasks over real DDS; captured {len(decisions)} "
          f"decisions (rejected={bridge.rejected})")
    ex = explain_decision(store, "rmf:delivery-82:award")
    ex2 = explain_decision(store, "rmf:delivery-83:award")
    if ex:
        print(f"  delivery-82 -> {ex['selected_action']} / {ex['outcome']}")
    if ex2:
        print(f"  delivery-83 -> {ex2['selected_action']} / {ex2['outcome']}")

    ok = (
        len(decisions) == 2
        and ex is not None and ex["selected_action"] == "robot-3" and ex["outcome"] == "succeeded"
        and ex2 is not None and ex2["selected_action"] == "robot-7" and ex2["outcome"] == "failed"
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
