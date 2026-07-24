"""Content-hashed references to external snapshots.

OWE never copies raw sensor data; it stores a *reference* plus a content hash of
the referenced bytes (a rosbag2/MCAP slice, a trace, a world-state snapshot). The
hash makes the link verifiable: if the referenced artifact is later altered, the
stored hash no longer matches, so provenance can detect a broken or tampered
reference without holding the data itself.
"""

from __future__ import annotations

import hashlib

from .envelope import WorldStateRef


def content_hash(data: bytes) -> str:
    """Return a ``sha256:<hex>`` content hash of ``data``."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def snapshot_ref(
    data: bytes,
    *,
    map_id: str | None = None,
    map_version: str | None = None,
    trace_ref: str | None = None,
) -> WorldStateRef:
    """Build a ``WorldStateRef`` that hashes ``data`` and records where it lives."""
    return WorldStateRef(
        map_id=map_id,
        map_version=map_version,
        snapshot_hash=content_hash(data),
        trace_ref=trace_ref,
    )


def verify_ref(ref: WorldStateRef, data: bytes) -> bool:
    """True iff ``data`` matches the reference's recorded content hash.

    Returns False when the reference carries no hash — an unverifiable reference
    is treated as not-verified, never as trusted.
    """
    if not ref.snapshot_hash:
        return False
    return ref.snapshot_hash == content_hash(data)
