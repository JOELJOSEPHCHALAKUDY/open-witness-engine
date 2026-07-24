"""Ordering and idempotency primitives.

A provenance store must reconstruct per-source order even when wall clocks skew,
detect gaps in a source's sequence, deduplicate replays, and reason about causal
ordering across sources with a vector clock.
"""

from open_witness_engine.ordering import (
    IdempotencyLedger,
    SequenceTracker,
    VectorClock,
)


class TestSequenceTracker:
    def test_accepts_monotonic_increasing_sequence(self) -> None:
        t = SequenceTracker()
        assert t.observe("robot-1", 0) is True
        assert t.observe("robot-1", 1) is True
        assert t.observe("robot-1", 2) is True

    def test_rejects_duplicate_or_regressing_sequence(self) -> None:
        t = SequenceTracker()
        t.observe("robot-1", 5)
        assert t.observe("robot-1", 5) is False
        assert t.observe("robot-1", 3) is False

    def test_tracks_sources_independently(self) -> None:
        t = SequenceTracker()
        assert t.observe("robot-1", 0) is True
        assert t.observe("robot-2", 0) is True

    def test_detects_gaps(self) -> None:
        t = SequenceTracker()
        t.observe("robot-1", 0)
        assert t.missing_before("robot-1", 3) == [1, 2]

    def test_no_gap_when_contiguous(self) -> None:
        t = SequenceTracker()
        t.observe("robot-1", 0)
        t.observe("robot-1", 1)
        assert t.missing_before("robot-1", 2) == []


class TestIdempotencyLedger:
    def test_first_key_is_new_then_seen(self) -> None:
        ledger = IdempotencyLedger()
        assert ledger.seen("k1") is False
        ledger.record("k1")
        assert ledger.seen("k1") is True

    def test_record_is_idempotent(self) -> None:
        ledger = IdempotencyLedger()
        assert ledger.record("k1") is True   # newly recorded
        assert ledger.record("k1") is False  # duplicate


class TestVectorClock:
    def test_tick_increments_own_component(self) -> None:
        vc = VectorClock()
        vc.tick("robot-1")
        vc.tick("robot-1")
        assert vc["robot-1"] == 2

    def test_merge_takes_componentwise_max(self) -> None:
        a = VectorClock({"robot-1": 2, "robot-2": 1})
        b = VectorClock({"robot-1": 1, "robot-2": 5, "robot-3": 1})
        a.merge(b)
        assert dict(a) == {"robot-1": 2, "robot-2": 5, "robot-3": 1}

    def test_happens_before_is_strict(self) -> None:
        a = VectorClock({"robot-1": 1})
        b = VectorClock({"robot-1": 2})
        assert a.happens_before(b) is True
        assert b.happens_before(a) is False
        assert a.happens_before(a) is False  # not strictly before itself

    def test_concurrent_clocks_are_not_ordered(self) -> None:
        a = VectorClock({"robot-1": 1})
        b = VectorClock({"robot-2": 1})
        assert a.happens_before(b) is False
        assert b.happens_before(a) is False
        assert a.concurrent_with(b) is True


def test_sequence_tracker_missing_before_rejects_unknown_source() -> None:
    t = SequenceTracker()
    # An unseen source has no established floor; nothing is "missing" yet.
    assert t.missing_before("ghost", 3) == []
