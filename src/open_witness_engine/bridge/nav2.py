"""Nav2 adapter — behavior-tree navigation decisions.

Nav2 behavior trees expose understandable task transitions: the planner chosen,
the route considered and taken, recovery attempts, and the action outcome. Each
transition is a decision: the considered routes are candidates, the chosen route
is the selected action, and the behavior-tree result is the outcome.

As with the RMF adapter, the ROS I/O is a seam; this module maps an
already-deserialized record into a ``DecisionObservation`` and is pure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..envelope import CandidateAction, Outcome, OutcomeStatus, Software
from .capture import DecisionObservation

_SOURCE = "nav2-bridge"

_RESULT_MAP = {
    "succeeded": OutcomeStatus.SUCCEEDED,
    "success": OutcomeStatus.SUCCEEDED,
    "failed": OutcomeStatus.FAILED,
    "failure": OutcomeStatus.FAILED,
    "aborted": OutcomeStatus.ABORTED,
    "canceled": OutcomeStatus.ABORTED,
    "cancelled": OutcomeStatus.ABORTED,
    "recovery_required": OutcomeStatus.RECOVERY_REQUIRED,
    "running": OutcomeStatus.IN_PROGRESS,
}


def _result_status(raw: str | None) -> OutcomeStatus:
    if raw is None:
        return OutcomeStatus.IN_PROGRESS
    return _RESULT_MAP.get(raw.strip().lower(), OutcomeStatus.IN_PROGRESS)


def nav2_bt_to_observation(record: dict[str, Any]) -> DecisionObservation:
    """Map a Nav2 behavior-tree transition into a normalized decision observation."""
    robot = str(record["robot"])
    nav_goal_id = str(record["nav_goal_id"])
    rejected: dict[str, str] = dict(record.get("rejected", {}))
    candidates = [
        CandidateAction(
            action=str(route),
            rejected_reasons=[rejected[route]] if route in rejected else [],
        )
        for route in record.get("considered", [])
    ]
    software = None
    if record.get("planner"):
        software = Software(
            planner=str(record["planner"]),
            planner_version=record.get("planner_version"),
        )
    return DecisionObservation(
        source=_SOURCE,
        event_id=f"nav2:{robot}:{nav_goal_id}",
        robot_id=robot,
        action_goal_id=nav_goal_id,
        wall_time=datetime.fromisoformat(record["wall_time"]),
        monotonic_ns=int(record["monotonic_ns"]),
        goal=str(record["goal"]),
        candidate_actions=candidates,
        selected_action=str(record["chosen"]),
        decision_reason=record.get("reason"),
        software=software,
        outcome=Outcome(
            status=_result_status(record.get("result")),
            recovery=record.get("recovery"),
        ),
    )
