"""Typed causal graph over decision records.

This is the layer robot observability tools lack: not just *what happened*, but
*why decisions relate*. Edges are typed, so lineage ("what caused this"),
versioning ("what supersedes this"), and invalidation are first-class and
machine-checkable — rather than an after-the-fact LLM narration.

The graph stores node ids only (decision ids or referenced entities); envelopes
themselves live in the provenance store.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CausalEdgeType(StrEnum):
    CAUSED_BY = "caused_by"
    CHOSEN_OVER = "chosen_over"
    CONSTRAINED_BY = "constrained_by"
    EXECUTED_AS = "executed_as"
    RESULTED_IN = "resulted_in"
    CORRECTED_BY = "corrected_by"
    INVALIDATED_BY = "invalidated_by"
    SUPERSEDED_BY = "superseded_by"


class CausalEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    src: str
    type: CausalEdgeType
    dst: str


class DecisionGraph:
    """An append-only directed multigraph of typed causal edges."""

    def __init__(self) -> None:
        # Insertion-ordered, de-duplicated per source node.
        self._out: dict[str, list[CausalEdge]] = {}

    def link(self, src: str, edge_type: CausalEdgeType, dst: str) -> CausalEdge:
        """Record a typed edge ``src --edge_type--> dst``. Idempotent."""
        edge = CausalEdge(src=src, type=edge_type, dst=dst)
        bucket = self._out.setdefault(src, [])
        if edge not in bucket:
            bucket.append(edge)
        return edge

    def edges_from(self, src: str, edge_type: CausalEdgeType | None = None) -> list[CausalEdge]:
        edges = self._out.get(src, [])
        if edge_type is None:
            return list(edges)
        return [e for e in edges if e.type is edge_type]

    def ancestors(self, node: str, edge_type: CausalEdgeType) -> list[str]:
        """Nodes reachable from ``node`` along ``edge_type``, nearest first, cycle-safe."""
        seen: set[str] = set()
        order: list[str] = []
        frontier = [e.dst for e in self.edges_from(node, edge_type)]
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            order.append(current)
            frontier.extend(e.dst for e in self.edges_from(current, edge_type))
        return order

    def current_version(self, node: str) -> str:
        """Follow ``superseded_by`` to the tip. Cycle-safe (returns the last node reached)."""
        seen: set[str] = {node}
        current = node
        while True:
            nxt = self.edges_from(current, CausalEdgeType.SUPERSEDED_BY)
            if not nxt or nxt[0].dst in seen:
                return current
            current = nxt[0].dst
            seen.add(current)

    def is_invalidated(self, node: str) -> bool:
        return bool(self.edges_from(node, CausalEdgeType.INVALIDATED_BY))
