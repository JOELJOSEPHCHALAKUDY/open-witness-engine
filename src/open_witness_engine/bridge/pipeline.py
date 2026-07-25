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

from ..store import DuplicateDecisionError, ProvenanceStore
from .capture import DecisionObservation
from .errors import MalformedRecordError
from .spool import BoundedSpool

Adapter = Callable[[dict[str, Any]], DecisionObservation]

# The ways a record is known to be "bad" — a missing/garbage field
# (MalformedRecordError), a value the model rejects (ValidationError), a failed
# numeric/type coercion (ValueError/TypeError), or a key collision at write time
# (DuplicateDecisionError). These are named so a *record* fault is attributed to
# the record; anything else escaping the store is attributed to storage instead.
_REJECTABLE = (
    MalformedRecordError,
    ValidationError,
    ValueError,
    TypeError,
    DuplicateDecisionError,
)


@dataclass(frozen=True)
class DrainReport:
    accepted: int
    rejected: int
    dropped: int
    # Records lost because the *store* failed, not because they were bad. Kept
    # apart from ``rejected`` because they mean opposite things to an operator:
    # rejected says fix the adapter, storage_failures says the disk is dying.
    storage_failures: int = 0


class Bridge:
    """Non-blocking, fail-open capture pipeline into a provenance store."""

    def __init__(self, store: ProvenanceStore, *, capacity: int = 1000) -> None:
        self._store = store
        self._spool: BoundedSpool[DecisionObservation] = BoundedSpool(capacity=capacity)
        self._seq: dict[str, int] = {}
        self._rejected = 0
        self._storage_failures = 0

    @property
    def rejected(self) -> int:
        return self._rejected

    @property
    def dropped(self) -> int:
        return self._spool.dropped

    @property
    def storage_failures(self) -> int:
        return self._storage_failures

    def capture(self, adapter: Adapter, record: dict[str, Any]) -> bool:
        """Map a source record and offer it to the spool. Never raises.

        Returns True if accepted cleanly; False if the record was malformed
        (counted as rejected) or its acceptance dropped an older spooled item.

        The catch is deliberately total. Adapters are the project's extension
        point, so third-party ones will raise exceptions this module has never
        heard of, and an unlisted exception type is not a reason to take a robot
        down. ``BaseException`` is left alone so Ctrl-C and SystemExit still work.
        """
        try:
            obs = adapter(record)
        except Exception:
            self._rejected += 1
            return False
        return self._spool.offer(obs)

    def drain(self) -> DrainReport:
        """Translate and append spooled observations; absorb per-record failures.

        Two distinct faults are separated here. A record that cannot become a
        valid envelope is *rejected*; a healthy record the store refuses to take
        is a *storage failure*. Both are absorbed — invariant 3 says ingestion
        never blocks a robot — but only the second means the fleet is losing
        provenance it should be keeping.
        """
        accepted = 0
        for obs in self._spool.drain():
            next_seq = self._seq.get(obs.source, 0)
            try:
                envelope = obs.to_envelope(source_seq=next_seq)
            except Exception:
                self._rejected += 1
                continue
            try:
                self._store.append(envelope)
            except _REJECTABLE:
                self._rejected += 1
                continue
            except Exception:
                self._storage_failures += 1
                continue
            self._seq[obs.source] = next_seq + 1
            accepted += 1
        return DrainReport(
            accepted=accepted,
            rejected=self._rejected,
            dropped=self._spool.dropped,
            storage_failures=self._storage_failures,
        )
