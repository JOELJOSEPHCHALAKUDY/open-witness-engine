"""At-scale volume tests.

Property tests use small inputs to explore many shapes; these use large inputs to
catch scaling and correctness-at-volume issues (a fleet-day of decisions, a long
supersession chain, sustained spool overflow). Deterministic, no randomness in the
assertions.
"""

from datetime import UTC, datetime

from open_witness_engine.bridge.capture import DecisionObservation
from open_witness_engine.bridge.spool import BoundedSpool
from open_witness_engine.causal import CausalEdgeType, DecisionGraph
from open_witness_engine.envelope import (
    CandidateAction,
    Outcome,
    OutcomeStatus,
    RobotDecisionEnvelope,
    Software,
)
from open_witness_engine.query import outcome_rates_by_version
from open_witness_engine.store import InMemoryProvenanceStore

_T0 = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _obs(robot: str, seq: int, *, version: str, status: OutcomeStatus) -> RobotDecisionEnvelope:
    obs = DecisionObservation(
        source="vol",
        event_id=f"{robot}:{seq}",
        robot_id=robot,
        wall_time=_T0,
        monotonic_ns=seq + 1,
        goal="Deliver container to station B",
        candidate_actions=[
            CandidateAction(action="route-west"),
            CandidateAction(action="route-east"),
        ],
        selected_action="route-west",
        software=Software(planner="nav2-smac", planner_version=version),
        outcome=Outcome(status=status),
    )
    return obs.to_envelope(source_seq=seq)


def test_spool_sustained_overflow_conserves_100k_items() -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=1000)
    offered = 0
    drained = 0
    # Offers vastly outpace drains, so the spool overflows continuously — the
    # realistic case where a robot emits faster than the bridge drains.
    for i in range(100_000):
        spool.offer(i)
        offered += 1
        assert len(spool) <= 1000  # invariant holds throughout, under overflow
        if i % 5_000 == 0:
            drained += len(spool.drain(max_items=50))
    drained += len(spool.drain())
    assert offered == drained + spool.dropped  # nothing lost unaccounted-for
    assert spool.dropped > 90_000  # overflow genuinely and heavily exercised


def test_store_20k_decisions_across_50_robots_dedups_and_orders() -> None:
    store = InMemoryProvenanceStore()
    versions = ["1.0", "2.0", "3.0"]
    per_robot = 400
    robots = [f"robot-{r}" for r in range(50)]
    for robot in robots:
        for seq in range(per_robot):
            version = versions[seq % 3]
            # v3.0 regresses: every 4th decision needs recovery.
            status = (
                OutcomeStatus.RECOVERY_REQUIRED
                if version == "3.0" and seq % 4 == 0
                else OutcomeStatus.SUCCEEDED
            )
            store.append(_obs(robot, seq, version=version, status=status))

    total = 50 * per_robot
    assert len(list(store.all())) == total

    # Full replay of every record is a no-op (idempotent).
    for robot in robots:
        for seq in range(per_robot):
            store.append(
                _obs(robot, seq, version=versions[seq % 3], status=OutcomeStatus.SUCCEEDED)
            )
    assert len(list(store.all())) == total

    # Per-source ordering holds at volume.
    for robot in robots:
        seqs = [e.source_seq for e in store.by_source(robot)]
        assert seqs == list(range(per_robot))

    # Version regression is detectable in the aggregate.
    rates = outcome_rates_by_version(store)
    assert rates["1.0"]["failure_rate"] == 0.0
    assert rates["2.0"]["failure_rate"] == 0.0
    assert rates["3.0"]["failure_rate"] > 0.0


def test_store_missing_sequence_at_volume() -> None:
    store = InMemoryProvenanceStore()
    # 0..9999 with 4242 dropped, to prove gap detection scales and is exact.
    dropped = 4242
    for seq in range(10_000):
        if seq == dropped:
            continue
        store.append(_obs("robot-x", seq, version="1.0", status=OutcomeStatus.SUCCEEDED))
    assert store.missing_sequence("robot-x") == [dropped]


def test_causal_supersession_chain_10k_resolves_to_tip() -> None:
    g = DecisionGraph()
    for i in range(10_000):
        g.link(f"v{i}", CausalEdgeType.SUPERSEDED_BY, f"v{i + 1}")
    assert g.current_version("v0") == "v10000"
    assert g.current_version("v9999") == "v10000"


def test_causal_ancestors_deep_chain_returns_all() -> None:
    g = DecisionGraph()
    for i in range(5_000):
        g.link(f"d{i + 1}", CausalEdgeType.CAUSED_BY, f"d{i}")
    ancestors = g.ancestors("d5000", CausalEdgeType.CAUSED_BY)
    assert len(ancestors) == 5_000
    assert ancestors[0] == "d4999"
    assert ancestors[-1] == "d0"
