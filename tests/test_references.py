"""Content-hashed references to external snapshots (rosbag2 / trace / world state).

OWE stores *references* to the raw evidence, never the raw data. A reference
carries a content hash so the link is verifiable and tamper-evident: if the
referenced snapshot changes, the hash no longer matches.
"""


from open_witness_engine.references import content_hash, snapshot_ref, verify_ref


def test_content_hash_is_deterministic() -> None:
    assert content_hash(b"point-cloud-bytes") == content_hash(b"point-cloud-bytes")


def test_content_hash_changes_with_content() -> None:
    assert content_hash(b"a") != content_hash(b"b")


def test_content_hash_is_sha256_prefixed() -> None:
    h = content_hash(b"x")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_snapshot_ref_carries_hash_and_locator() -> None:
    ref = snapshot_ref(b"bag-bytes", trace_ref="mcap://bag-42#t=10.5")
    assert ref.snapshot_hash == content_hash(b"bag-bytes")
    assert ref.trace_ref == "mcap://bag-42#t=10.5"


def test_verify_detects_tampering() -> None:
    ref = snapshot_ref(b"original", trace_ref="mcap://bag-1")
    assert verify_ref(ref, b"original") is True
    assert verify_ref(ref, b"tampered") is False


def test_verify_false_when_no_hash() -> None:
    from open_witness_engine.envelope import WorldStateRef

    assert verify_ref(WorldStateRef(trace_ref="mcap://x"), b"anything") is False
