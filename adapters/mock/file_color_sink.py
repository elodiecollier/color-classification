"""Mock ColorSink: appends ColorRecords to local JSONL files.

Implements `ports.color_sink.ColorSink`. Two outputs under `out_dir` (default
`output/`):
  - `color_records.jsonl` — every published record (§8 schema, one JSON object
    per line); this is what `cli/search.py` queries.
  - `review_queue.jsonl`  — records with `needs_review=True`, for human triage.

Both files are truncated when the sink is opened (a run starts fresh). Usable as
a context manager. The Directus writer replaces this later with no caller changes.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

from core.models import ColorRecord


class FileColorSink:
    """`ColorSink` that writes JSONL, routing `needs_review` records aside."""

    def __init__(self, out_dir: str | Path = "output") -> None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        self.records_path = out / "color_records.jsonl"
        self.review_path = out / "review_queue.jsonl"
        self._records = self.records_path.open("w", encoding="utf-8")
        self._review = self.review_path.open("w", encoding="utf-8")

    def write(self, record: ColorRecord) -> None:
        target = self._review if record.needs_review else self._records
        target.write(record.model_dump_json() + "\n")
        target.flush()

    def close(self) -> None:
        self._records.close()
        self._review.close()

    def __enter__(self) -> "FileColorSink":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
