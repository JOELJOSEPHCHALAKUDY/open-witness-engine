"""Open-RMF adapter — task-assignment decisions.

Open-RMF task requests, bids, awards, execution, and failures are discrete and
auditable rather than hard real-time, which makes them the natural first capture
target for OWE. A task award is a decision: the bids are the candidates, the
awarded robot is the selected action, and the task result is the outcome.

The ROS I/O (subscribing to ``rmf_task_msgs``) is a seam left to a deployment.
This module maps an already-deserialized record (a plain dict) into a
``DecisionObservation`` and is pure and testable without ROS.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..envelope import CandidateAction, Outcome, OutcomeStatus
from .capture import DecisionObservation

_SOURCE = "rmf-bridge"

_STATUS_MAP = {
    "succeeded": OutcomeStatus.SUCCEEDED,
    "completed": OutcomeStatus.SUCCEEDED,
    "failed": OutcomeStatus.FAILED,
    "cancelled": OutcomeStatus.ABORTED,
    "aborted": OutcomeStatus.ABORTED,
    "recovery_required": OutcomeStatus.RECOVERY_REQUIRED,
    "executing": OutcomeStatus.IN_PROGRESS,
    "queued": OutcomeStatus.IN_PROGRESS,
}


def _outcome_status(raw: str | None) -> OutcomeStatus:
    """Map an RMF status string; unknown states are IN_PROGRESS, never dropped."""
    if raw is None:
        return OutcomeStatus.IN_PROGRESS
    return _STATUS_MAP.get(raw.strip().lower(), OutcomeStatus.IN_PROGRESS)


def rmf_task_award_to_observation(record: dict[str, Any]) -> DecisionObservation:
    """Map an RMF task-award record into a normalized decision observation."""
    task_id = str(record["task_id"])
    candidates = [
        CandidateAction(
            action=str(bid["robot"]),
            cost=bid.get("cost"),
            rejected_reasons=list(bid.get("rejected_reasons", [])),
        )
        for bid in record.get("bids", [])
    ]
    return DecisionObservation(
        source=_SOURCE,
        event_id=f"rmf:{task_id}:award",
        robot_id=str(record["awarded_robot"]),
        fleet_id=record.get("fleet"),
        task_id=task_id,
        wall_time=datetime.fromisoformat(record["wall_time"]),
        monotonic_ns=int(record["monotonic_ns"]),
        goal=str(record["goal"]),
        candidate_actions=candidates,
        selected_action=str(record["awarded_robot"]),
        decision_reason=record.get("reason"),
        outcome=Outcome(status=_outcome_status(record.get("status"))),
    )
