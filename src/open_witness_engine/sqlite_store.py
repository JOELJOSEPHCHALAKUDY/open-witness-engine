"""SQLite-backed provenance store — persistence behind the same contract.

Implements the ``ProvenanceStore`` behavior of ``InMemoryProvenanceStore`` but
durably, so decisions survive a restart. Append-only: corrections are new rows
linked by causal edges, never in-place mutation. Envelopes are stored as their
Pydantic JSON so the exact record round-trips. A Postgres backend can later
implement the same interface without changing any caller.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .causal import CausalEdge, CausalEdgeType, DecisionGraph
from .envelope import RobotDecisionEnvelope
from .store import DuplicateDecisionError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    seq            INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id    TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    source_id      TEXT NOT NULL,
    source_seq     INTEGER NOT NULL,
    payload        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_source ON decisions(source_id, source_seq);
CREATE TABLE IF NOT EXISTS edges (
    src   TEXT NOT NULL,
    type  TEXT NOT NULL,
    dst   TEXT NOT NULL,
    UNIQUE(src, type, dst)
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
"""


class SqliteProvenanceStore:
    """Durable append-only provenance store."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- writes ---

    def append(self, envelope: RobotDecisionEnvelope) -> None:
        key = envelope.idempotency_key
        existing = self._conn.execute(
            "SELECT decision_id FROM decisions WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if existing is not None:
            if existing["decision_id"] != envelope.decision_id:
                raise DuplicateDecisionError(
                    f"idempotency_key {key!r} already used for decision {existing['decision_id']!r}"
                )
            return  # idempotent replay
        self._conn.execute(
            "INSERT INTO decisions(decision_id, idempotency_key, source_id, source_seq, payload) "
            "VALUES(?, ?, ?, ?, ?)",
            (
                envelope.decision_id,
                key,
                envelope.source_id,
                envelope.source_seq,
                envelope.model_dump_json(),
            ),
        )
        self._conn.commit()

    def link(self, src: str, edge_type: CausalEdgeType, dst: str) -> CausalEdge:
        self._conn.execute(
            "INSERT OR IGNORE INTO edges(src, type, dst) VALUES(?, ?, ?)",
            (src, edge_type.value, dst),
        )
        self._conn.commit()
        return CausalEdge(src=src, type=edge_type, dst=dst)

    def supersede(self, *, old: str, new: str) -> CausalEdge:
        return self.link(old, CausalEdgeType.SUPERSEDED_BY, new)

    # --- reads ---

    def get(self, decision_id: str) -> RobotDecisionEnvelope | None:
        row = self._conn.execute(
            "SELECT payload FROM decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            return None
        return RobotDecisionEnvelope.model_validate_json(row["payload"])

    def all(self) -> Iterator[RobotDecisionEnvelope]:
        for row in self._conn.execute("SELECT payload FROM decisions ORDER BY seq"):
            yield RobotDecisionEnvelope.model_validate_json(row["payload"])

    def by_source(self, source_id: str) -> list[RobotDecisionEnvelope]:
        rows = self._conn.execute(
            "SELECT payload FROM decisions WHERE source_id = ? ORDER BY source_seq",
            (source_id,),
        ).fetchall()
        return [RobotDecisionEnvelope.model_validate_json(r["payload"]) for r in rows]

    def missing_sequence(self, source_id: str) -> list[int]:
        seqs = [
            int(r["source_seq"])
            for r in self._conn.execute(
                "SELECT source_seq FROM decisions WHERE source_id = ? ORDER BY source_seq",
                (source_id,),
            )
        ]
        if not seqs:
            return []
        present = set(seqs)
        return [s for s in range(seqs[0], seqs[-1]) if s not in present]

    def edges_from(self, src: str, edge_type: CausalEdgeType | None = None) -> list[CausalEdge]:
        if edge_type is None:
            rows = self._conn.execute(
                "SELECT src, type, dst FROM edges WHERE src = ? ORDER BY rowid", (src,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT src, type, dst FROM edges WHERE src = ? AND type = ? ORDER BY rowid",
                (src, edge_type.value),
            ).fetchall()
        return [
            CausalEdge(src=r["src"], type=CausalEdgeType(r["type"]), dst=r["dst"]) for r in rows
        ]

    def current_version(self, decision_id: str) -> str:
        """Follow superseded_by to the tip, cycle-safe."""
        seen = {decision_id}
        current = decision_id
        while True:
            nxt = self.edges_from(current, CausalEdgeType.SUPERSEDED_BY)
            if not nxt or nxt[0].dst in seen:
                return current
            current = nxt[0].dst
            seen.add(current)

    def graph_snapshot(self) -> DecisionGraph:
        """Rebuild an in-memory DecisionGraph from the persisted edges (for traversal)."""
        g = DecisionGraph()
        for r in self._conn.execute("SELECT src, type, dst FROM edges ORDER BY rowid"):
            g.link(r["src"], CausalEdgeType(r["type"]), r["dst"])
        return g
