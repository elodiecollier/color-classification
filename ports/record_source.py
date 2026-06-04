"""Port: where the records to classify come from (CLAUDE.md §11, §12).

Yields `MaterialRecord`s (core/models.py) — ids, optional swatch name, optional
image reference — mirroring the real persisted row shape so the fixture and the
eventual Directus source are interchangeable.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from core.models import MaterialRecord


class RecordSource(Protocol):
    """Source of the records to batch over."""

    def iter_records(self) -> Iterable[MaterialRecord]:
        """Yield each record to classify."""
        ...
