"""The Bridge facade — resilient wiring of adapter -> spool -> store.

This is the ergonomic and fail-open front door. A ROS callback calls
``bridge.capture(adapter, record)``, which never raises: a malformed record is
counted and dropped, a healthy one is offered to the bounded spool. A consumer
calls ``bridge.drain()`` to translate spooled observations into validated
envelopes and append them, absorbing any per-record validation failure so one
bad record can never stall capture for the rest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ..store import InMemoryProvenanceStore
from .capture import DecisionObservation
from .errors import MalformedRecordError
from .spool import BoundedSpool

Adapter = Callable[[dict[str, Any]], DecisionObservation]


@dataclass(frozen=True)
class DrainReport:
    accepted: int
    rejected: int
    dropped: int


class Bridge:
    """Non-blocking, fail-open capture pipeline into a provenance store."""

    def __init__(self, store: InMemoryProvenanceStore, *, capacity: int = 1000) -> None:
        self._store = store
        self._spool: BoundedSpool[DecisionObservation] = BoundedSpool(capacity=capacity)
        self._seq: dict[str, int] = {}
        self._rejected = 0

    @property
    def rejected(self) -> int:
        return self._rejected

    @property
    def dropped(self) -> int:
        return self._spool.dropped

    def capture(self, adapter: Adapter, record: dict[str, Any]) -> bool:
        """Map a source record and offer it to the spool. Never raises.

        Returns True if accepted cleanly; False if the record was malformed
        (counted as rejected) or its acceptance dropped an older spooled item.
        """
        try:
            obs = adapter(record)
        except MalformedRecordError:
            self._rejected += 1
            return False
        return self._spool.offer(obs)

    def drain(self) -> DrainReport:
        """Translate and append spooled observations; absorb per-record failures."""
        accepted = 0
        for obs in self._spool.drain():
            try:
                next_seq = self._seq.get(obs.source, 0)
                self._store.append(obs.to_envelope(source_seq=next_seq))
            except (ValidationError, ValueError):
                self._rejected += 1
                continue
            self._seq[obs.source] = next_seq + 1
            accepted += 1
        return DrainReport(accepted=accepted, rejected=self._rejected, dropped=self._spool.dropped)
