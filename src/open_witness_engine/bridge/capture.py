"""Normalized capture model and translation into the decision envelope.

A ``CaptureSource`` (a ROS adapter) yields source-agnostic
``DecisionObservation`` records. The bridge assigns a per-source sequence and
translates each into a validated ``RobotDecisionEnvelope``. Identity is derived
from the source event id so replays deduplicate in the provenance store.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..envelope import (
    CandidateAction,
    HumanOverride,
    Outcome,
    RobotDecisionEnvelope,
    Software,
    WorldStateRef,
)


class DecisionObservation(BaseModel):
    """A source-agnostic observation of one robot decision, before translation."""

    model_config = ConfigDict(frozen=True)

    source: str  # producer/adapter identity, e.g. "rmf-bridge"
    event_id: str  # stable id from the source system; drives dedup identity

    robot_id: str
    fleet_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    action_goal_id: str | None = None

    wall_time: datetime
    monotonic_ns: int = Field(ge=0)

    goal: str
    world_state_ref: WorldStateRef | None = None
    candidate_actions: list[CandidateAction] = Field(min_length=1)
    selected_action: str
    constraints: list[str] = Field(default_factory=list)
    decision_reason: str | None = None
    software: Software | None = None
    outcome: Outcome
    human_override: HumanOverride | None = None

    def to_envelope(self, *, source_seq: int) -> RobotDecisionEnvelope:
        """Translate into a validated envelope with a bridge-assigned sequence.

        ``decision_id`` and ``idempotency_key`` derive from source + event id, so
        the same source event always maps to the same identity regardless of the
        sequence number assigned at ingest time.
        """
        return RobotDecisionEnvelope(
            decision_id=self.event_id,
            robot_id=self.robot_id,
            fleet_id=self.fleet_id,
            mission_id=self.mission_id,
            task_id=self.task_id,
            action_goal_id=self.action_goal_id,
            wall_time=self.wall_time,
            monotonic_ns=self.monotonic_ns,
            source_seq=source_seq,
            idempotency_key=f"{self.source}:{self.event_id}",
            goal=self.goal,
            world_state_ref=self.world_state_ref,
            candidate_actions=list(self.candidate_actions),
            selected_action=self.selected_action,
            constraints=list(self.constraints),
            decision_reason=self.decision_reason,
            software=self.software,
            outcome=self.outcome,
            human_override=self.human_override,
        )


@runtime_checkable
class CaptureSource(Protocol):
    """A ROS adapter that yields decision observations.

    Implementations subscribe to a robot's ROS 2 graph and translate messages
    into ``DecisionObservation`` records. ``poll`` must be non-blocking.
    """

    def poll(self) -> Iterable[DecisionObservation]: ...
