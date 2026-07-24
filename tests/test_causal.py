"""Typed causal graph over decisions.

The causal graph is the differentiator: it records *why* decisions relate, with
typed edges (caused_by, chosen_over, corrected_by, superseded_by, ...). It must
enforce edge typing, support lineage traversal, and be safe on cycles.
"""

from open_witness_engine.causal import CausalEdge, CausalEdgeType, DecisionGraph


def test_edge_types_cover_the_decision_vocabulary() -> None:
    names = {e.value for e in CausalEdgeType}
    assert names == {
        "caused_by",
        "chosen_over",
        "constrained_by",
        "executed_as",
        "resulted_in",
        "corrected_by",
        "invalidated_by",
        "superseded_by",
    }


def test_add_and_query_typed_edges() -> None:
    g = DecisionGraph()
    g.link("d2", CausalEdgeType.CAUSED_BY, "d1")
    g.link("d2", CausalEdgeType.CHOSEN_OVER, "alt-1")
    assert g.edges_from("d2") == [
        CausalEdge(src="d2", type=CausalEdgeType.CAUSED_BY, dst="d1"),
        CausalEdge(src="d2", type=CausalEdgeType.CHOSEN_OVER, dst="alt-1"),
    ]


def test_edges_filtered_by_type() -> None:
    g = DecisionGraph()
    g.link("d2", CausalEdgeType.CAUSED_BY, "d1")
    g.link("d2", CausalEdgeType.CHOSEN_OVER, "alt-1")
    caused = g.edges_from("d2", edge_type=CausalEdgeType.CAUSED_BY)
    assert [e.dst for e in caused] == ["d1"]


def test_duplicate_edges_are_deduplicated() -> None:
    g = DecisionGraph()
    g.link("d2", CausalEdgeType.CAUSED_BY, "d1")
    g.link("d2", CausalEdgeType.CAUSED_BY, "d1")
    assert len(g.edges_from("d2")) == 1


def test_lineage_follows_caused_by_chain() -> None:
    g = DecisionGraph()
    g.link("d3", CausalEdgeType.CAUSED_BY, "d2")
    g.link("d2", CausalEdgeType.CAUSED_BY, "d1")
    # Ancestors of d3 along caused_by, nearest first.
    assert g.ancestors("d3", CausalEdgeType.CAUSED_BY) == ["d2", "d1"]


def test_lineage_is_cycle_safe() -> None:
    g = DecisionGraph()
    g.link("a", CausalEdgeType.CAUSED_BY, "b")
    g.link("b", CausalEdgeType.CAUSED_BY, "a")  # cycle
    result = g.ancestors("a", CausalEdgeType.CAUSED_BY)
    assert set(result) == {"b", "a"}  # terminates, visits each once


def test_current_version_follows_superseded_by_to_the_tip() -> None:
    g = DecisionGraph()
    g.link("v1", CausalEdgeType.SUPERSEDED_BY, "v2")
    g.link("v2", CausalEdgeType.SUPERSEDED_BY, "v3")
    assert g.current_version("v1") == "v3"
    assert g.current_version("v3") == "v3"  # tip supersedes nothing


def test_invalidated_nodes_are_reported() -> None:
    g = DecisionGraph()
    g.link("d9", CausalEdgeType.INVALIDATED_BY, "d10")
    assert g.is_invalidated("d9") is True
    assert g.is_invalidated("d10") is False


def test_edges_from_unknown_node_is_empty() -> None:
    g = DecisionGraph()
    assert g.edges_from("nope") == []
