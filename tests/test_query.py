"""Decision-provenance queries.

These are the questions the raw logs cannot answer: reconstruct why a decision
was made (the factual tuple, not an LLM narration), diff outcomes across software
versions to find which change regressed, and find prior similar situations.
"""

from datetime import UTC, datetime, timedelta

import pytest

from open_witness_engine.envelope import (
    CandidateAction,
    Outcome,
    OutcomeStatus,
    RobotDecisionEnvelope,
    Software,
)
from open_witness_engine.query import (
    explain_decision,
    outcome_rates_by_version,
    similar_prior_decisions,
)
from open_witness_engine.store import InMemoryProvenanceStore

_T0 = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _env(
    seq: int,
    decision_id: str,
    *,
    goal: str = "Deliver container to station B",
    selected: str = "route-west",
    status: OutcomeStatus = OutcomeStatus.SUCCEEDED,
    planner_version: str | None = None,
    robot: str = "robot-3",
) -> RobotDecisionEnvelope:
    return RobotDecisionEnvelope(
        decision_id=decision_id,
        robot_id=robot,
        wall_time=_T0 + timedelta(seconds=seq),
        monotonic_ns=1_000 * (seq + 1),
        source_seq=seq,
        idempotency_key=f"{robot}:{decision_id}",
        goal=goal,
        candidate_actions=[
            CandidateAction(action="route-west", cost=14.2),
            CandidateAction(action="route-east", cost=11.8, rejected_reasons=["safety closure"]),
        ],
        selected_action=selected,
        decision_reason="Lowest feasible route cost",
        software=(
            Software(planner="nav2-smac", planner_version=planner_version)
            if planner_version
            else None
        ),
        outcome=Outcome(status=status),
    )


def test_explain_returns_the_factual_decision_tuple() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "d-0"))
    ex = explain_decision(store, "d-0")
    assert ex is not None
    assert ex["goal"] == "Deliver container to station B"
    assert ex["selected_action"] == "route-west"
    assert ex["reason"] == "Lowest feasible route cost"
    # Rejected alternatives are surfaced with their reasons.
    assert ex["rejected"] == [{"action": "route-east", "reasons": ["safety closure"]}]
    assert ex["outcome"] == "succeeded"


def test_explain_unknown_decision_is_none() -> None:
    store = InMemoryProvenanceStore()
    assert explain_decision(store, "ghost") is None


def test_outcome_rates_by_version_isolates_a_regression() -> None:
    store = InMemoryProvenanceStore()
    # v1: all succeed. v2: half require recovery — a regression.
    store.append(_env(0, "a", planner_version="1.0", status=OutcomeStatus.SUCCEEDED))
    store.append(_env(1, "b", planner_version="1.0", status=OutcomeStatus.SUCCEEDED))
    store.append(_env(2, "c", planner_version="2.0", status=OutcomeStatus.SUCCEEDED))
    store.append(_env(3, "d", planner_version="2.0", status=OutcomeStatus.RECOVERY_REQUIRED))
    store.append(_env(4, "e", planner_version="2.0", status=OutcomeStatus.FAILED))

    rates = outcome_rates_by_version(store)
    assert rates["1.0"]["total"] == 2
    assert rates["1.0"]["failure_rate"] == 0.0
    assert rates["2.0"]["total"] == 3
    # 2 of 3 non-success (recovery_required + failed).
    assert rates["2.0"]["failure_rate"] == pytest.approx(2 / 3)


def test_similar_prior_decisions_matches_goal_and_excludes_self() -> None:
    store = InMemoryProvenanceStore()
    store.append(_env(0, "old-1", goal="Deliver container to station B"))
    store.append(_env(1, "old-2", goal="Charge at dock 4"))
    store.append(_env(2, "current", goal="Deliver container to station B"))

    similar = similar_prior_decisions(store, "current")
    ids = [e.decision_id for e in similar]
    assert ids == ["old-1"]  # same goal, earlier, not itself


def test_similar_prior_decisions_unknown_is_empty() -> None:
    store = InMemoryProvenanceStore()
    assert similar_prior_decisions(store, "ghost") == []
