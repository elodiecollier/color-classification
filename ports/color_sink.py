"""Port: where finished ColorRecords go (CLAUDE.md §8, §11, §12).

The §8 schema is sink-agnostic; this port makes the sink swappable so a Directus
writer can replace the file writer later with NO pipeline changes (§4). Records
with `needs_review=True` are routed to a review queue — whether that's a second
file (mock) or a status field (Directus) is the adapter's business, not the
caller's.
"""

from __future__ import annotations

from typing import Protocol

from core.models import ColorRecord


class ColorSink(Protocol):
    """Destination for finished ColorRecords."""

    def write(self, record: ColorRecord) -> None:
        """Persist one record (routing `needs_review=True` to the review queue)."""
        ...

    def close(self) -> None:
        """Flush and release any resources (file handles, connections)."""
        ...
