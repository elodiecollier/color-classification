"""Mock RecordSource: loads MaterialRecords from a JSON fixture.

Implements `ports.record_source.RecordSource`. The fixture is a JSON array of
objects matching `core.models.MaterialRecord`. Validation errors fail loudly —
fixtures are ours, so a bad one is a bug, not data noise.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from core.models import MaterialRecord


class FixtureRecordSource:
    """`RecordSource` backed by a JSON fixture file."""

    def __init__(self, path: str | Path = "fixtures/records.json") -> None:
        self._path = Path(path)

    def iter_records(self) -> Iterator[MaterialRecord]:
        rows = json.loads(self._path.read_text())
        for row in rows:
            yield MaterialRecord(**row)
