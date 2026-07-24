"""Normalized capture model and translation to the decision envelope.

Adapters produce a source-agnostic DecisionObservation; the bridge assigns a
per-source sequence and translates it into a validated RobotDecisionEnvelope.
Identity and idempotency must be stable so replays deduplicate.
"""

from datetime import UTC, datetime

from open_witness_engine.bridge.capture import DecisionObservation
from open_witness_engine.envelope import (
    CandidateAction,
    Outcome,
    OutcomeStatus,
    RobotDecisionEnvelope,
)

_T0 = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _obs(event_id: str = "rmf:task-82:awarded") -> DecisionObservation:
    return DecisionObservation(
        source="rmf-bridge",
        event_id=event_id,
        robot_id="robot-3",
        fleet_id="warehouse-a",
        wall_time=_T0,
        monotonic_ns=123456789,
        goal="Deliver container to station B",
        candidate_actions=[
            CandidateAction(action="robot-3", cost=11.8),
            CandidateAction(action="robot-7", cost=14.2, rejected_reasons=["busy"]),
        ],
        selected_action="robot-3",
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED),
    )


def test_translation_produces_valid_envelope() -> None:
    env = _obs().to_envelope(source_seq=0)
    assert isinstance(env, RobotDecisionEnvelope)
    assert env.robot_id == "robot-3"
    assert env.selected_action == "robot-3"
    assert env.source_seq == 0


def test_decision_id_and_idempotency_key_are_stable_from_event_id() -> None:
    a = _obs("rmf:task-82:awarded").to_envelope(source_seq=0)
    b = _obs("rmf:task-82:awarded").to_envelope(source_seq=5)
    # Same source event -> same identity regardless of assigned sequence.
    assert a.decision_id == b.decision_id
    assert a.idempotency_key == b.idempotency_key
    assert a.idempotency_key == "rmf-bridge:rmf:task-82:awarded"


def test_distinct_events_get_distinct_identity() -> None:
    a = _obs("rmf:task-82:awarded").to_envelope(source_seq=0)
    b = _obs("rmf:task-83:awarded").to_envelope(source_seq=1)
    assert a.idempotency_key != b.idempotency_key


def test_selected_action_must_be_a_candidate_after_translation() -> None:
    import pytest
    from pydantic import ValidationError

    obs = DecisionObservation(
        source="rmf-bridge",
        event_id="e1",
        robot_id="robot-3",
        wall_time=_T0,
        monotonic_ns=1,
        goal="g",
        candidate_actions=[CandidateAction(action="a")],
        selected_action="not-a-candidate",
        outcome=Outcome(status=OutcomeStatus.FAILED),
    )
    with pytest.raises(ValidationError):
        obs.to_envelope(source_seq=0)
