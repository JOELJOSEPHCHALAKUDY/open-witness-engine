"""Open-RMF and Nav2 adapter mappings.

The ROS I/O is a seam; the *mapping* from a source record (a plain dict, as the
ROS message fields would deserialize) into a DecisionObservation is pure and
tested here with synthetic inputs. Open-RMF task assignment and Nav2 behavior-tree
transitions are both discrete and auditable — the right altitude for OWE.
"""

from datetime import UTC, datetime

from open_witness_engine.bridge.nav2 import nav2_bt_to_observation
from open_witness_engine.bridge.rmf import rmf_task_award_to_observation
from open_witness_engine.envelope import OutcomeStatus

_T0 = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def test_rmf_task_award_maps_bids_to_candidates_and_winner_to_selected() -> None:
    record = {
        "task_id": "delivery-82",
        "fleet": "warehouse-a",
        "wall_time": _T0.isoformat(),
        "monotonic_ns": 111,
        "goal": "Deliver container to station B",
        "bids": [
            {"robot": "robot-3", "cost": 11.8},
            {"robot": "robot-7", "cost": 14.2, "rejected_reasons": ["busy"]},
        ],
        "awarded_robot": "robot-3",
        "status": "succeeded",
    }
    obs = rmf_task_award_to_observation(record)
    assert obs.source == "rmf-bridge"
    assert obs.event_id == "rmf:delivery-82:award"
    assert obs.robot_id == "robot-3"
    assert obs.task_id == "delivery-82"
    assert {c.action for c in obs.candidate_actions} == {"robot-3", "robot-7"}
    assert obs.selected_action == "robot-3"
    assert obs.outcome.status is OutcomeStatus.SUCCEEDED
    # Round-trips through validation.
    env = obs.to_envelope(source_seq=0)
    assert env.selected_action == "robot-3"


def test_rmf_unknown_status_falls_back_to_in_progress() -> None:
    record = {
        "task_id": "t1",
        "wall_time": _T0.isoformat(),
        "monotonic_ns": 1,
        "goal": "g",
        "bids": [{"robot": "r1", "cost": 1.0}],
        "awarded_robot": "r1",
        "status": "weird-unmapped-state",
    }
    obs = rmf_task_award_to_observation(record)
    assert obs.outcome.status is OutcomeStatus.IN_PROGRESS


def test_nav2_bt_maps_recovery_and_planner_choice() -> None:
    record = {
        "robot": "robot-3",
        "nav_goal_id": "nav-14",
        "wall_time": _T0.isoformat(),
        "monotonic_ns": 222,
        "goal": "Navigate to station B",
        "planner": "nav2-smac",
        "planner_version": "1.2.3",
        "considered": ["route-west", "route-east"],
        "chosen": "route-west",
        "rejected": {"route-east": "temporary safety closure"},
        "result": "recovery_required",
        "recovery": "replan",
    }
    obs = nav2_bt_to_observation(record)
    assert obs.robot_id == "robot-3"
    assert obs.action_goal_id == "nav-14"
    assert obs.event_id == "nav2:robot-3:nav-14"
    assert obs.selected_action == "route-west"
    east = next(c for c in obs.candidate_actions if c.action == "route-east")
    assert east.rejected_reasons == ["temporary safety closure"]
    assert obs.software is not None
    assert obs.software.planner_version == "1.2.3"
    assert obs.outcome.status is OutcomeStatus.RECOVERY_REQUIRED
    assert obs.outcome.recovery == "replan"
    obs.to_envelope(source_seq=0)  # validates
