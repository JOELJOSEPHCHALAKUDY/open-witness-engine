"""Decision-provenance queries over a provenance store.

These answer the questions raw robot logs cannot: *why* a decision was made,
*which software version* regressed an outcome, and *what was decided before* in a
similar situation. They return factual structures; turning them into prose (with
citations) is a downstream, optional LLM step — never the source of truth.

v0 uses exact goal matching for similarity. Semantic retrieval is a later
milestone; keeping the interface stable now lets it drop in without changing
callers.
"""

from __future__ import annotations

from typing import Any

from .envelope import OutcomeStatus, RobotDecisionEnvelope
from .store import ProvenanceStore

_SUCCESS = {OutcomeStatus.SUCCEEDED, OutcomeStatus.IN_PROGRESS}


def explain_decision(store: ProvenanceStore, decision_id: str) -> dict[str, Any] | None:
    """Reconstruct the factual decision tuple for ``decision_id``.

    Returns the goal, selected action and reason, the rejected alternatives with
    their reasons, and the outcome — the evidence an explanation must cite.
    """
    env = store.get(decision_id)
    if env is None:
        return None
    rejected = [
        {"action": c.action, "reasons": list(c.rejected_reasons)}
        for c in env.candidate_actions
        if c.action != env.selected_action and c.rejected_reasons
    ]
    return {
        "decision_id": env.decision_id,
        "robot_id": env.robot_id,
        "goal": env.goal,
        "selected_action": env.selected_action,
        "reason": env.decision_reason,
        "constraints": list(env.constraints),
        "rejected": rejected,
        "outcome": env.outcome.status.value,
        "software": env.software.model_dump(exclude_none=True) if env.software else None,
    }


def outcome_rates_by_version(store: ProvenanceStore) -> dict[str, dict[str, Any]]:
    """Aggregate outcome rates per planner version, to localize a regression.

    Answers "which software change increased blocked-path failures": a version
    whose ``failure_rate`` jumps versus its predecessor is the suspect.
    """
    buckets: dict[str, dict[str, int]] = {}
    for env in store.all():
        if env.software is None or env.software.planner_version is None:
            continue
        version = env.software.planner_version
        bucket = buckets.setdefault(version, {"total": 0, "failures": 0})
        bucket["total"] += 1
        if env.outcome.status not in _SUCCESS:
            bucket["failures"] += 1
    return {
        version: {
            "total": b["total"],
            "failures": b["failures"],
            "failure_rate": (b["failures"] / b["total"]) if b["total"] else 0.0,
        }
        for version, b in buckets.items()
    }


def similar_prior_decisions(
    store: ProvenanceStore,
    decision_id: str,
    *,
    limit: int = 10,
) -> list[RobotDecisionEnvelope]:
    """Prior decisions for the same goal — "what did we do last time".

    Excludes the decision itself and any later decisions. v0 matches goals
    exactly; semantic matching is a later milestone behind this same signature.
    """
    target = store.get(decision_id)
    if target is None:
        return []
    prior = [
        env
        for env in store.all()
        if env.decision_id != decision_id
        and env.goal == target.goal
        and env.wall_time < target.wall_time
    ]
    prior.sort(key=lambda e: e.wall_time, reverse=True)
    return prior[:limit]
