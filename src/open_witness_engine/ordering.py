"""Ordering and idempotency primitives for the provenance store.

Reimplemented cleanly from Open Timeline Engine's proven design (per-source
sequence, idempotency key, vector clock) — no code dependency on that project.
These let the store reconstruct order under wall-clock skew, detect dropped
records, deduplicate replays, and reason about causal ordering across sources.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping


class SequenceTracker:
    """Tracks the highest per-source sequence number seen, and detects gaps.

    A source is any producer identity (a robot, a bridge instance). Sequence
    numbers are expected to be monotonically increasing per source.
    """

    def __init__(self) -> None:
        self._highest: dict[str, int] = {}

    def observe(self, source: str, seq: int) -> bool:
        """Record a sequence number. Returns True if it advances the source.

        A duplicate or regressing sequence returns False and is not applied.
        """
        current = self._highest.get(source)
        if current is not None and seq <= current:
            return False
        self._highest[source] = seq
        return True

    def missing_before(self, source: str, seq: int) -> list[int]:
        """Sequence numbers between the source's floor and ``seq`` never seen.

        An unknown source has no established floor, so nothing is reported missing.
        """
        current = self._highest.get(source)
        if current is None:
            return []
        return list(range(current + 1, seq))


class IdempotencyLedger:
    """Remembers which idempotency keys have been applied."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    def seen(self, key: str) -> bool:
        return key in self._keys

    def record(self, key: str) -> bool:
        """Record a key. Returns True if newly recorded, False if a duplicate."""
        if key in self._keys:
            return False
        self._keys.add(key)
        return True


class VectorClock:
    """A vector clock over source identities for cross-source causal ordering."""

    def __init__(self, initial: Mapping[str, int] | None = None) -> None:
        self._clock: dict[str, int] = dict(initial) if initial else {}

    def __getitem__(self, source: str) -> int:
        return self._clock.get(source, 0)

    def __iter__(self) -> Iterator[str]:
        return iter(self._clock)

    def keys(self) -> Iterator[str]:
        return iter(self._clock)

    def items(self) -> Iterator[tuple[str, int]]:
        return iter(self._clock.items())

    def tick(self, source: str) -> None:
        self._clock[source] = self._clock.get(source, 0) + 1

    def merge(self, other: VectorClock) -> None:
        """Take the component-wise maximum with ``other`` (in place)."""
        for source in set(self._clock) | set(other._clock):
            self._clock[source] = max(self[source], other[source])

    def happens_before(self, other: VectorClock) -> bool:
        """True iff this clock strictly precedes ``other`` (Lamport ordering)."""
        sources = set(self._clock) | set(other._clock)
        if all(self[s] == other[s] for s in sources):
            return False  # equal clocks are not strictly before
        return all(self[s] <= other[s] for s in sources)

    def concurrent_with(self, other: VectorClock) -> bool:
        """True iff neither clock precedes the other."""
        return (
            not self.happens_before(other)
            and not other.happens_before(self)
            and not self._equal(other)
        )

    def _equal(self, other: VectorClock) -> bool:
        sources = set(self._clock) | set(other._clock)
        return all(self[s] == other[s] for s in sources)

    def snapshot(self) -> dict[str, int]:
        return dict(self._clock)
