"""RobotDecisionEnvelope v1 model validation.

The envelope is the factual record of a single decision. It must validate its
own integrity: the selected action must be one of the candidates, the outcome
status must be known, and the ordering/identity fields must be present.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from open_witness_engine.envelope import (
    CandidateAction,
    HumanOverride,
    Outcome,
    OutcomeStatus,
    RobotDecisionEnvelope,
)


def _valid_kwargs() -> dict[str, Any]:
    return {
        "decision_id": "d-1",
        "robot_id": "robot-3",
        "fleet_id": "warehouse-a",
        "mission_id": "mission-291",
        "task_id": "delivery-82",
        "wall_time": datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        "monotonic_ns": 123456789,
        "source_seq": 9931,
        "idempotency_key": "robot-3:9931",
        "goal": "Deliver container to station B",
        "candidate_actions": [
            CandidateAction(action="route-west", cost=14.2),
            CandidateAction(
                action="route-east", cost=11.8, rejected_reasons=["safety closure"]
            ),
        ],
        "selected_action": "route-west",
        "constraints": ["avoid-zone-east"],
        "decision_reason": "Lowest feasible route cost",
        "outcome": Outcome(
            status=OutcomeStatus.RECOVERY_REQUIRED, error="path_obstructed", recovery="replan"
        ),
    }


def test_valid_envelope_round_trips() -> None:
    env = RobotDecisionEnvelope(**_valid_kwargs())
    assert env.schema_version == 1
    assert env.selected_action == "route-west"
    assert env.outcome.status is OutcomeStatus.RECOVERY_REQUIRED
    assert env.human_override is None


def test_selected_action_must_be_a_candidate() -> None:
    kwargs = _valid_kwargs()
    kwargs["selected_action"] = "route-north"  # not among candidates
    with pytest.raises(ValidationError) as exc:
        RobotDecisionEnvelope(**kwargs)
    assert "selected_action" in str(exc.value)


def test_requires_at_least_one_candidate() -> None:
    kwargs = _valid_kwargs()
    kwargs["candidate_actions"] = []
    kwargs["selected_action"] = "route-west"
    with pytest.raises(ValidationError):
        RobotDecisionEnvelope(**kwargs)


def test_unknown_outcome_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Outcome(status="exploded")  # type: ignore[arg-type]


def test_wall_time_must_be_timezone_aware() -> None:
    kwargs = _valid_kwargs()
    kwargs["wall_time"] = datetime(2026, 7, 24, 12, 0)  # naive
    with pytest.raises(ValidationError):
        RobotDecisionEnvelope(**kwargs)


def test_human_override_is_optional_and_typed() -> None:
    kwargs = _valid_kwargs()
    kwargs["human_override"] = HumanOverride(
        operator_id="op-7", action="hold", reason="blocked aisle"
    )
    env = RobotDecisionEnvelope(**kwargs)
    assert env.human_override is not None
    assert env.human_override.operator_id == "op-7"


def test_envelope_is_immutable() -> None:
    env = RobotDecisionEnvelope(**_valid_kwargs())
    with pytest.raises(ValidationError):
        env.selected_action = "route-east"


def test_json_schema_export_matches_schema_version() -> None:
    schema = RobotDecisionEnvelope.model_json_schema()
    assert schema["properties"]["schema_version"]["const"] == 1
