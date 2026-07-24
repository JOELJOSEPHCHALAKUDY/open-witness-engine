"""Nav2 adapter — behavior-tree navigation decisions.

Nav2 behavior trees expose understandable task transitions: the planner chosen,
the route considered and taken, recovery attempts, and the action outcome. Each
transition is a decision: the considered routes are candidates, the chosen route
is the selected action, and the behavior-tree result is the outcome.

As with the RMF adapter, the ROS I/O is a seam; this module maps an
already-deserialized record into a ``DecisionObservation`` and is pure.
"""

from __future__ import annotations

from typing import Any

from ..envelope import CandidateAction, Outcome, OutcomeStatus, Software
from .capture import DecisionObservation
from .errors import parse_timestamp, require

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
    """Map a Nav2 behavior-tree transition into a normalized decision observation.

    Raises ``MalformedRecordError`` (with context) on a missing required field or
    an unparseable timestamp.
    """
    robot = str(require(record, "robot", source=_SOURCE))
    nav_goal_id = str(require(record, "nav_goal_id", source=_SOURCE))
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
        wall_time=parse_timestamp(record, "wall_time", source=_SOURCE),
        monotonic_ns=int(require(record, "monotonic_ns", source=_SOURCE)),
        goal=str(require(record, "goal", source=_SOURCE)),
        candidate_actions=candidates,
        selected_action=str(require(record, "chosen", source=_SOURCE)),
        decision_reason=record.get("reason"),
        software=software,
        outcome=Outcome(
            status=_result_status(record.get("result")),
            recovery=record.get("recovery"),
        ),
    )
