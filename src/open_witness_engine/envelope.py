"""RobotDecisionEnvelope v1 — the factual record of a single robot decision.

Mirrors ``schemas/robot-decision-envelope.v1.json``. This captures *what was
decided and why*, not commands: OWE observes and explains decisions, it never
makes or executes them. Factual variables and causal links are stored here;
human-readable narration is a downstream concern.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"
    ABORTED = "aborted"
    IN_PROGRESS = "in_progress"


class CandidateAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    cost: float | None = None
    rejected_reasons: list[str] = Field(default_factory=list)


class WorldStateRef(BaseModel):
    """A reference to external state/recording — never the raw data itself."""

    model_config = ConfigDict(frozen=True)

    map_id: str | None = None
    map_version: str | None = None
    snapshot_hash: str | None = None
    trace_ref: str | None = None


class Software(BaseModel):
    model_config = ConfigDict(frozen=True)

    planner: str | None = None
    planner_version: str | None = None
    config_hash: str | None = None
    build_commit: str | None = None


class Outcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: OutcomeStatus
    error: str | None = None
    recovery: str | None = None


class HumanOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    operator_id: str | None = None
    action: str | None = None
    reason: str | None = None


class RobotDecisionEnvelope(BaseModel):
    """A single task-level decision, observation-only."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    decision_id: str
    robot_id: str
    fleet_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    action_goal_id: str | None = None

    wall_time: datetime
    monotonic_ns: int = Field(ge=0)
    source_seq: int = Field(ge=0)
    idempotency_key: str

    goal: str
    world_state_ref: WorldStateRef | None = None
    candidate_actions: list[CandidateAction] = Field(min_length=1)
    selected_action: str
    constraints: list[str] = Field(default_factory=list)
    decision_reason: str | None = None
    software: Software | None = None
    outcome: Outcome
    human_override: HumanOverride | None = None

    # The producer's source identity for ordering; defaults to robot_id.
    @property
    def source_id(self) -> str:
        return self.robot_id

    @field_validator("wall_time")
    @classmethod
    def _wall_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("wall_time must be timezone-aware (UTC)")
        return value

    @model_validator(mode="after")
    def _selected_action_is_a_candidate(self) -> RobotDecisionEnvelope:
        candidates = {c.action for c in self.candidate_actions}
        if self.selected_action not in candidates:
            raise ValueError(
                f"selected_action {self.selected_action!r} is not among candidate_actions"
            )
        return self

    @staticmethod
    def json_schema() -> dict[str, Any]:
        return RobotDecisionEnvelope.model_json_schema()
