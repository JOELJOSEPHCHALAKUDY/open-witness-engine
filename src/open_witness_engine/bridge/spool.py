"""Non-blocking bounded spool — the fail-open transport.

The producer side (a ROS callback on a robot) must never block or raise. The
spool holds a fixed number of items; on overflow it drops the oldest and counts
the drop. Data loss under sustained overload is acceptable by design — OWE is a
non-authoritative memory layer, never on the robot's critical path — but it is
bounded and observable via ``dropped``.
"""

from __future__ import annotations

from collections import deque


class BoundedSpool[T]:
    """Non-blocking bounded FIFO of any spooled payload (a DecisionObservation in practice)."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._items: deque[T] = deque()
        self._dropped = 0

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._items)

    def offer(self, item: T) -> bool:
        """Add an item without ever blocking or raising.

        Returns True if accepted cleanly, False if accepting it required dropping
        the oldest item (the item is still stored; the return value signals loss).
        """
        dropped_here = False
        if len(self._items) >= self._capacity:
            self._items.popleft()
            self._dropped += 1
            dropped_here = True
        self._items.append(item)
        return not dropped_here

    def drain(self, max_items: int | None = None) -> list[T]:
        """Remove and return spooled items in offer order (oldest first)."""
        if max_items is None:
            out = list(self._items)
            self._items.clear()
            return out
        out = []
        for _ in range(min(max_items, len(self._items))):
            out.append(self._items.popleft())
        return out
