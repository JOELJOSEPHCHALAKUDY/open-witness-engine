"""Bridge error types and safe field extraction.

A malformed source record (a missing field, an unparseable timestamp) must be
rejectable with context, not crash the drain loop. Adapters raise
``MalformedRecordError``; the pipeline absorbs it and counts the rejection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class MalformedRecordError(Exception):
    """A source record could not be mapped into a decision observation."""

    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"[{source}] {detail}")


def require(record: dict[str, Any], key: str, *, source: str) -> Any:
    """Return ``record[key]`` or raise MalformedRecordError naming the field."""
    if key not in record or record[key] is None:
        raise MalformedRecordError(source, f"missing required field {key!r}")
    return record[key]


def parse_timestamp(record: dict[str, Any], key: str, *, source: str) -> datetime:
    """Parse an ISO-8601 timestamp field, raising MalformedRecordError on junk."""
    raw = require(record, key, source=source)
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError as exc:
        raise MalformedRecordError(
            source, f"field {key!r} is not an ISO-8601 datetime: {raw!r}"
        ) from exc
