"""Concurrency safety of the spool.

On a real robot the producer (a ROS callback) and the consumer (the bridge
drain) run on different threads. offer() does check-length-then-pop-then-append
and mutates a drop counter; without a lock those are races that can lose or
double-count items. This hammers the spool from many threads and asserts the
conservation invariant still holds exactly.
"""

import threading

from open_witness_engine.bridge.spool import BoundedSpool


def test_conservation_holds_under_concurrent_offer_and_drain() -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=256)
    per_thread = 5000
    n_producers = 8
    drained: list[int] = []
    stop = threading.Event()

    def produce(base: int) -> None:
        for i in range(per_thread):
            spool.offer(base * per_thread + i)  # must never raise across threads

    def consume() -> None:
        while not stop.is_set():
            drained.extend(spool.drain(max_items=64))

    producers = [threading.Thread(target=produce, args=(b,)) for b in range(n_producers)]
    consumer = threading.Thread(target=consume)
    consumer.start()
    for p in producers:
        p.start()
    for p in producers:
        p.join()
    stop.set()
    consumer.join()
    drained.extend(spool.drain())  # final sweep

    offered = n_producers * per_thread
    # Nothing lost or double-counted: everything offered was drained or dropped.
    assert len(drained) + spool.dropped == offered
    assert len(spool) == 0


def test_no_duplicate_items_survive_concurrency() -> None:
    spool: BoundedSpool[int] = BoundedSpool(capacity=1024)
    per_thread = 3000
    n_producers = 6
    seen: list[int] = []
    stop = threading.Event()

    def produce(base: int) -> None:
        for i in range(per_thread):
            spool.offer(base * per_thread + i)

    def consume() -> None:
        while not stop.is_set():
            seen.extend(spool.drain(max_items=128))

    producers = [threading.Thread(target=produce, args=(b,)) for b in range(n_producers)]
    consumer = threading.Thread(target=consume)
    consumer.start()
    for p in producers:
        p.start()
    for p in producers:
        p.join()
    stop.set()
    consumer.join()
    seen.extend(spool.drain())

    # Every drained id is unique — no item was handed out twice by a torn drain.
    assert len(seen) == len(set(seen))
