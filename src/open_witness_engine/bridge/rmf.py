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

from typing import Any

from ..envelope import CandidateAction, Outcome, OutcomeStatus
from .capture import DecisionObservation
from .errors import parse_timestamp, require

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
    """Map an RMF task-award record into a normalized decision observation.

    Raises ``MalformedRecordError`` (with context) on a missing required field
    or an unparseable timestamp, so the caller can reject-and-count rather than
    crash the drain loop.
    """
    task_id = str(require(record, "task_id", source=_SOURCE))
    awarded = str(require(record, "awarded_robot", source=_SOURCE))
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
        robot_id=awarded,
        fleet_id=record.get("fleet"),
        task_id=task_id,
        wall_time=parse_timestamp(record, "wall_time", source=_SOURCE),
        monotonic_ns=int(require(record, "monotonic_ns", source=_SOURCE)),
        goal=str(require(record, "goal", source=_SOURCE)),
        candidate_actions=candidates,
        selected_action=awarded,
        decision_reason=record.get("reason"),
        outcome=Outcome(status=_outcome_status(record.get("status"))),
    )
