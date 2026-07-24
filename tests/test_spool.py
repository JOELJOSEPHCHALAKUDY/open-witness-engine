"""Non-blocking bounded spool — the fail-open transport invariant.

A robot process must never block, stall, or crash because OWE is slow or full.
The spool accepts offers without ever blocking or raising; under overflow it
drops the oldest record and counts the drop, so data loss is bounded, observable,
and never back-pressures the producer.
"""

from open_witness_engine.bridge.spool import BoundedSpool


def test_offer_accepts_within_capacity() -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=3)
    assert spool.offer(1) is True
    assert spool.offer(2) is True
    assert len(spool) == 2
    assert spool.dropped == 0


def test_offer_never_blocks_or_raises_when_full() -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=2)
    spool.offer(1)
    spool.offer(2)
    # Overflow must return without blocking or raising.
    result = spool.offer(3)
    assert result is False  # signalled a drop occurred, but did not raise
    assert len(spool) == 2


def test_overflow_drops_oldest_and_counts() -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=2)
    spool.offer(1)
    spool.offer(2)
    spool.offer(3)  # drops 1
    spool.offer(4)  # drops 2
    assert spool.drain() == [3, 4]
    assert spool.dropped == 2


def test_drain_returns_in_offer_order_and_empties() -> None:
    spool: BoundedSpool[str] = BoundedSpool(capacity=5)
    spool.offer("a")
    spool.offer("b")
    assert spool.drain() == ["a", "b"]
    assert len(spool) == 0
    assert spool.drain() == []


def test_capacity_must_be_positive() -> None:
    import pytest

    with pytest.raises(ValueError):
        BoundedSpool(capacity=0)


def test_drain_batch_limits_and_preserves_remainder() -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=5)
    for i in range(4):
        spool.offer(i)
    first = spool.drain(max_items=2)
    assert first == [0, 1]
    assert spool.drain() == [2, 3]
