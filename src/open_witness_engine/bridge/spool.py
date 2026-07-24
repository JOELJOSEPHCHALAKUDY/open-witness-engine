"""Non-blocking bounded spool — the fail-open transport.

The producer side (a ROS callback on a robot) must never block or raise. The
spool holds a fixed number of items; on overflow it drops the oldest and counts
the drop. Data loss under sustained overload is acceptable by design — OWE is a
non-authoritative memory layer, never on the robot's critical path — but it is
bounded and observable via ``dropped``.
"""

from __future__ import annotations

import threading
from collections import deque


class BoundedSpool[T]:
    """Non-blocking bounded FIFO of any spooled payload (a DecisionObservation in practice).

    Thread-safe: the producer (a ROS callback) and the consumer (the bridge drain)
    run on different threads, so ``offer`` (a check-pop-append compound plus a drop
    counter) and ``drain`` are guarded by a lock. The lock is held only for O(items
    moved) pointer work and never across I/O, so it does not make ``offer`` block on
    anything external — the fail-open guarantee is preserved.
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._items: deque[T] = deque()
        self._dropped = 0
        self._lock = threading.Lock()

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def offer(self, item: T) -> bool:
        """Add an item without ever blocking or raising.

        Returns True if accepted cleanly, False if accepting it required dropping
        the oldest item (the item is still stored; the return value signals loss).
        """
        with self._lock:
            dropped_here = False
            if len(self._items) >= self._capacity:
                self._items.popleft()
                self._dropped += 1
                dropped_here = True
            self._items.append(item)
            return not dropped_here

    def drain(self, max_items: int | None = None) -> list[T]:
        """Remove and return spooled items in offer order (oldest first)."""
        with self._lock:
            if max_items is None:
                out = list(self._items)
                self._items.clear()
                return out
            out = []
            for _ in range(min(max_items, len(self._items))):
                out.append(self._items.popleft())
            return out
