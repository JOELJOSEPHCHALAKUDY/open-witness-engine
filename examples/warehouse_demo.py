"""Minimal working example: a warehouse shift, end to end, no ROS required.

Run it:  python examples/warehouse_demo.py

It feeds Open-RMF and Nav2 style records through the fail-open Bridge into a
persistent SQLite store, links a causal chain, then answers the questions OWE
exists for. This is the same path a live ROS node drives — only the transport
differs.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from open_witness_engine.bridge.nav2 import nav2_bt_to_observation
from open_witness_engine.bridge.pipeline import Bridge
from open_witness_engine.bridge.rmf import rmf_task_award_to_observation
from open_witness_engine.causal import CausalEdgeType
from open_witness_engine.query import (
    explain_decision,
    outcome_rates_by_version,
    similar_prior_decisions,
)
from open_witness_engine.sqlite_store import SqliteProvenanceStore

T0 = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)


def ts(secs: int) -> str:
    return (T0 + timedelta(seconds=secs)).isoformat()


def main() -> None:
    db = Path(tempfile.mkdtemp()) / "warehouse.owe.db"
    store = SqliteProvenanceStore(db)
    bridge = Bridge(store)

    # RMF awards delivery-82 to robot-3 (robot-7 out-bid: low battery).
    bridge.capture(rmf_task_award_to_observation, {
        "task_id": "delivery-82", "fleet": "warehouse-a", "wall_time": ts(5),
        "monotonic_ns": 5_000_000, "goal": "Deliver container to station B",
        "reason": "lowest feasible bid",
        "bids": [{"robot": "robot-3", "cost": 11.8},
                 {"robot": "robot-7", "cost": 14.2, "rejected_reasons": ["battery < 30%"]}],
        "awarded_robot": "robot-3", "status": "executing",
    })

    # Nav2 picks route-west, hits an obstruction (v1.3.0).
    bridge.capture(nav2_bt_to_observation, {
        "robot": "robot-3", "nav_goal_id": "nav-14", "wall_time": ts(12), "monotonic_ns": 12_000_000,
        "goal": "Navigate to station B", "planner": "nav2-smac", "planner_version": "1.3.0",
        "considered": ["route-west", "route-east"], "chosen": "route-west",
        "rejected": {"route-east": "longer by 3.4m"}, "result": "recovery_required", "recovery": "replan",
    })
    # Recovery: replans to route-east, succeeds.
    bridge.capture(nav2_bt_to_observation, {
        "robot": "robot-3", "nav_goal_id": "nav-15", "wall_time": ts(40), "monotonic_ns": 40_000_000,
        "goal": "Navigate to station B", "planner": "nav2-smac", "planner_version": "1.3.0",
        "considered": ["route-east"], "chosen": "route-east", "result": "succeeded",
    })
    report = bridge.drain()
    store.link("nav2:robot-3:nav-15", CausalEdgeType.CAUSED_BY, "nav2:robot-3:nav-14")

    # A prior good run on v1.2.0, for the version comparison.
    bridge.capture(nav2_bt_to_observation, {
        "robot": "robot-9", "nav_goal_id": "nav-1", "wall_time": ts(100), "monotonic_ns": 100_000_000,
        "goal": "Navigate to station B", "planner": "nav2-smac", "planner_version": "1.2.0",
        "considered": ["route-west"], "chosen": "route-west", "result": "succeeded",
    })
    bridge.drain()

    print(f"captured {report.accepted + 1} decisions into {db}\n")

    print("Q: Why was robot-3 assigned delivery-82?")
    ex = explain_decision(store, "rmf:delivery-82:award")
    print(f"   -> {ex['selected_action']} ({ex['reason']}); rejected: {ex['rejected']}\n")

    print("Q: Why did navigation enter recovery?")
    ex = explain_decision(store, "nav2:robot-3:nav-14")
    print(f"   -> chose {ex['selected_action']}, rejected {ex['rejected']}, outcome={ex['outcome']}\n")

    print("Q: What caused the successful nav?")
    print(f"   -> {store.edges_from('nav2:robot-3:nav-15', CausalEdgeType.CAUSED_BY)[0].dst}\n")

    print("Q: Which planner version is regressing?")
    for ver, s in sorted(outcome_rates_by_version(store).items()):
        print(f"   {ver}: {s['failures']}/{s['total']} non-success = {s['failure_rate']:.0%}")

    print("\nQ: What did we do before for this goal?")
    for e in similar_prior_decisions(store, "nav2:robot-3:nav-15"):
        print(f"   - {e.wall_time.time()}  {e.decision_id} -> {e.selected_action}")

    store.close()


if __name__ == "__main__":
    main()
