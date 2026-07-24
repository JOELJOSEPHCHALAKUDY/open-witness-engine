"""Property-based tests: invariants over thousands of generated scenarios.

Where the other tests pin specific hand-picked cases, these assert invariants
that must hold for *any* input, and let Hypothesis generate many scenarios
(1000 per headline property) to try to break them — including shrinking to a
minimal counterexample when one is found.
"""

from datetime import UTC, datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from open_witness_engine.bridge.capture import DecisionObservation
from open_witness_engine.bridge.spool import BoundedSpool
from open_witness_engine.causal import CausalEdgeType, DecisionGraph
from open_witness_engine.envelope import (
    CandidateAction,
    Outcome,
    OutcomeStatus,
    RobotDecisionEnvelope,
)
from open_witness_engine.ordering import VectorClock
from open_witness_engine.store import InMemoryProvenanceStore

MANY = settings(max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
_T0 = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


# --- Spool: conservation and safety invariants ---------------------------------

_spool_ops = st.lists(
    st.one_of(
        st.tuples(st.just("offer"), st.integers()),
        st.tuples(st.just("drain"), st.integers(min_value=0, max_value=5)),
    ),
    max_size=200,
)


@MANY
@given(capacity=st.integers(min_value=1, max_value=32), ops=_spool_ops)
def test_spool_conserves_every_item_and_never_exceeds_capacity(
    capacity: int, ops: list[tuple[str, int]]
) -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=capacity)
    offered = 0
    drained = 0
    for kind, arg in ops:
        if kind == "offer":
            spool.offer(arg)  # must never raise
            offered += 1
        else:
            drained += len(spool.drain(max_items=arg))
        assert len(spool) <= capacity  # never over capacity, ever
    drained += len(spool.drain())
    # Nothing vanishes unaccounted-for: everything offered was drained or dropped.
    assert offered == drained + spool.dropped


# --- VectorClock: strict partial order ----------------------------------------

_clocks = st.dictionaries(
    st.sampled_from(["a", "b", "c", "d"]),
    st.integers(min_value=0, max_value=6),
    max_size=4,
).map(VectorClock)


@MANY
@given(a=_clocks, b=_clocks)
def test_happens_before_is_antisymmetric(a: VectorClock, b: VectorClock) -> None:
    assert not (a.happens_before(b) and b.happens_before(a))


@MANY
@given(a=_clocks)
def test_happens_before_is_irreflexive(a: VectorClock) -> None:
    assert not a.happens_before(a)


@settings(max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
@given(a=_clocks, b=_clocks, c=_clocks)
def test_happens_before_is_transitive(a: VectorClock, b: VectorClock, c: VectorClock) -> None:
    if a.happens_before(b) and b.happens_before(c):
        assert a.happens_before(c)


@MANY
@given(a=_clocks, b=_clocks)
def test_concurrency_is_symmetric(a: VectorClock, b: VectorClock) -> None:
    assert a.concurrent_with(b) == b.concurrent_with(a)


# --- Causal graph: traversal always terminates, even on cyclic graphs ---------

_nodes = st.sampled_from(["n0", "n1", "n2", "n3", "n4"])
_graph_edges = st.lists(
    st.tuples(_nodes, st.sampled_from(list(CausalEdgeType)), _nodes), max_size=40
)


def _build_graph(edges: list[tuple[str, CausalEdgeType, str]]) -> DecisionGraph:
    g = DecisionGraph()
    for src, etype, dst in edges:
        g.link(src, etype, dst)
    return g


@MANY
@given(edges=_graph_edges, start=_nodes)
def test_ancestors_terminates_with_unique_nodes(
    edges: list[tuple[str, CausalEdgeType, str]], start: str
) -> None:
    g = _build_graph(edges)
    result = g.ancestors(start, CausalEdgeType.CAUSED_BY)
    assert len(result) == len(set(result))  # each node at most once (cycle-safe)


@MANY
@given(edges=_graph_edges, start=_nodes)
def test_current_version_terminates_and_is_a_node(
    edges: list[tuple[str, CausalEdgeType, str]], start: str
) -> None:
    g = _build_graph(edges)
    tip = g.current_version(start)  # must not loop forever on cyclic supersedes
    assert isinstance(tip, str)


@MANY
@given(edges=_graph_edges)
def test_edges_are_deduplicated(edges: list[tuple[str, CausalEdgeType, str]]) -> None:
    g = _build_graph(edges)
    for src in {e[0] for e in edges}:
        out = g.edges_from(src)
        assert len(out) == len(set(out))


# --- Envelope: valid decisions always round-trip -------------------------------


@st.composite
def _envelopes(draw: st.DrawFn) -> RobotDecisionEnvelope:
    actions = draw(st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=6, unique=True))
    selected = draw(st.sampled_from(actions))
    return RobotDecisionEnvelope(
        decision_id=draw(st.text(min_size=1, max_size=12)),
        robot_id=draw(st.text(min_size=1, max_size=8)),
        wall_time=_T0,
        monotonic_ns=draw(st.integers(min_value=0, max_value=10**12)),
        source_seq=draw(st.integers(min_value=0, max_value=10**6)),
        idempotency_key=draw(st.text(min_size=1, max_size=16)),
        goal=draw(st.text(min_size=1, max_size=20)),
        candidate_actions=[CandidateAction(action=a) for a in actions],
        selected_action=selected,
        outcome=Outcome(status=draw(st.sampled_from(list(OutcomeStatus)))),
    )


@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
@given(env=_envelopes())
def test_envelope_round_trips_through_serialization(env: RobotDecisionEnvelope) -> None:
    restored = RobotDecisionEnvelope.model_validate(env.model_dump())
    assert restored == env
    assert restored.selected_action in {c.action for c in restored.candidate_actions}


# --- Store: append-only, idempotent, ordered under arbitrary interleavings -----


@settings(
    max_examples=300,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    rows=st.lists(
        st.tuples(
            st.sampled_from(["robot-a", "robot-b", "robot-c"]),
            st.integers(min_value=0, max_value=50),
        ),
        max_size=60,
    )
)
def test_store_dedups_and_orders_for_any_interleaving(rows: list[tuple[str, int]]) -> None:
    store = InMemoryProvenanceStore()
    seen: set[tuple[str, int]] = set()
    for robot, seq in rows:
        obs = DecisionObservation(
            source="gen",
            event_id=f"{robot}:{seq}",
            robot_id=robot,
            wall_time=_T0,
            monotonic_ns=1,
            goal="g",
            candidate_actions=[CandidateAction(action="x")],
            selected_action="x",
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED),
        )
        store.append(obs.to_envelope(source_seq=seq))
        seen.add((robot, seq))
    # De-dup: exactly one record per distinct (robot, seq).
    assert len(list(store.all())) == len(seen)
    # Ordering: per source, records are returned sorted by source_seq.
    for robot in {r for r, _ in rows}:
        seqs = [e.source_seq for e in store.by_source(robot)]
        assert seqs == sorted(seqs)
