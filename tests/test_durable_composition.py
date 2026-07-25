"""Composition tests: the durable store wired into the Bridge.

The unit suites cover each piece on its own. These cover them *together*, under
the threading and failure conditions a fleet actually runs — which is the only
configuration that ships. Invariant 3 in AGENTS.md ("ingestion is bounded-queue
and fail-open") is what these defend: a sick disk must degrade capture, never
raise into the robot's thread.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from open_witness_engine.bridge.pipeline import Bridge
from open_witness_engine.bridge.rmf import rmf_task_award_to_observation
from open_witness_engine.sqlite_store import SqliteProvenanceStore
from open_witness_engine.store import ProvenanceStore


def award(task_id: str = "t1") -> dict[str, Any]:
    return {
        "task_id": task_id,
        "awarded_robot": "robot-3",
        "fleet": "fleet-a",
        "goal": "deliver-82",
        "wall_time": "2026-07-25T09:00:00Z",
        "monotonic_ns": 1_000,
        "status": "completed",
        "bids": [
            {"robot": "robot-3", "cost": 1.0},
            {"robot": "robot-7", "cost": 9.0, "rejected_reasons": ["battery < 30%"]},
        ],
    }


def test_durable_store_accepts_the_provenance_store_protocol(tmp_path: Path) -> None:
    """The advertised swap: any ProvenanceStore backs the Bridge, not just the in-memory one.

    Annotated as the protocol on purpose — ``mypy --strict`` is the real assertion
    here, so a Bridge bound to a concrete class fails the type gate, not just runtime.
    """
    store: ProvenanceStore = SqliteProvenanceStore(tmp_path / "p.db")
    bridge = Bridge(store)

    assert bridge.capture(rmf_task_award_to_observation, award()) is True
    assert bridge.drain().accepted == 1


def test_durable_store_is_usable_from_another_thread(tmp_path: Path) -> None:
    """A ROS drain timer runs on a different thread than the one that opened the DB."""
    store = SqliteProvenanceStore(tmp_path / "p.db")
    written: list[int] = []
    escaped: list[BaseException] = []

    def worker() -> None:
        try:
            bridge = Bridge(store)
            bridge.capture(rmf_task_award_to_observation, award())
            bridge.drain()
            written.append(len(list(store.all())))
        except BaseException as exc:  # noqa: BLE001 - catching anything is the point
            escaped.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert not escaped, f"durable store raised across threads: {escaped[0]!r}"
    assert written == [1]


def test_drain_absorbs_storage_failure(tmp_path: Path) -> None:
    """Fail-open: a dead database must never raise into the caller."""
    store = SqliteProvenanceStore(tmp_path / "p.db")
    bridge = Bridge(store)
    bridge.capture(rmf_task_award_to_observation, award())
    store.close()  # disk full, file removed, handle dead

    report = bridge.drain()  # must not raise

    assert report.accepted == 0
    assert report.storage_failures == 1


def test_storage_failure_is_counted_apart_from_malformed_input(tmp_path: Path) -> None:
    """Two very different operator signals: fix your adapter vs. your disk is dying."""
    store = SqliteProvenanceStore(tmp_path / "p.db")
    bridge = Bridge(store)

    bridge.capture(rmf_task_award_to_observation, {"task_id": "no-other-fields"})
    assert bridge.rejected == 1
    assert bridge.storage_failures == 0

    bridge.capture(rmf_task_award_to_observation, award())
    store.close()
    bridge.drain()

    assert bridge.rejected == 1, "a storage fault must not be blamed on the record"
    assert bridge.storage_failures == 1


def test_capture_absorbs_an_adapter_error_outside_the_known_set(tmp_path: Path) -> None:
    """A bid missing its ``robot`` key raises KeyError from inside the adapter.

    Fail-open cannot depend on having enumerated every exception an adapter might
    throw — third-party adapters will raise things this project has never seen.
    """
    store = SqliteProvenanceStore(tmp_path / "p.db")
    bridge = Bridge(store)
    malformed = award()
    malformed["bids"] = [{"cost": 1.0}]  # no "robot" key -> KeyError

    assert bridge.capture(rmf_task_award_to_observation, malformed) is False
    assert bridge.rejected == 1


def test_capture_keeps_working_after_the_store_dies(tmp_path: Path) -> None:
    """The robot must keep running even when provenance can no longer be written."""
    store = SqliteProvenanceStore(tmp_path / "p.db")
    bridge = Bridge(store)
    store.close()

    for i in range(50):
        bridge.capture(rmf_task_award_to_observation, award(f"t{i}"))
        bridge.drain()  # must not raise, 50 times over

    assert bridge.storage_failures == 50


def test_concurrent_producers_with_a_single_drain_thread(tmp_path: Path) -> None:
    """The real ROS shape: several callback threads capture, one timer drains."""
    store = SqliteProvenanceStore(tmp_path / "p.db")
    bridge = Bridge(store, capacity=2_000)
    producers = 8
    per_producer = 50
    escaped: list[BaseException] = []
    start = threading.Barrier(producers)

    def produce(worker_id: int) -> None:
        try:
            start.wait()
            for i in range(per_producer):
                bridge.capture(rmf_task_award_to_observation, award(f"w{worker_id}-{i}"))
        except BaseException as exc:  # noqa: BLE001
            escaped.append(exc)

    threads = [threading.Thread(target=produce, args=(w,)) for w in range(producers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    report = bridge.drain()

    assert not escaped, f"capture raised under concurrency: {escaped[0]!r}"
    assert report.accepted == producers * per_producer
    assert len(list(store.all())) == producers * per_producer
