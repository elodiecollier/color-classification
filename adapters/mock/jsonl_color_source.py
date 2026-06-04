"""Load classified records back from run_batch's JSONL output (CLAUDE.md §10, §12).

The read-side counterpart to `FileColorSink`: reads the PUBLISHED records
(`output/color_records.jsonl`, skipping `review_queue.jsonl`) and joins each to
its `MaterialRecord` (from the fixtures) for display fields — yielding the
(MaterialRecord, ColorRecord) pairs `core.search.search()` consumes.

I/O lives here (an adapter), keeping `core/` pure. The Directus read-adapter
replaces this later with no change to `core.search`.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.models import ColorRecord, MaterialRecord


def load_classified(
    output_dir: str | Path = "output",
    fixtures: str | Path = "fixtures/records.json",
) -> list[tuple[MaterialRecord, ColorRecord]]:
    """Published (MaterialRecord, ColorRecord) pairs from run_batch's output.

    Returns [] if the output file doesn't exist yet (run_batch hasn't run).
    """
    materials = {
        row["material_id"]: MaterialRecord(**row)
        for row in json.loads(Path(fixtures).read_text())
    }

    path = Path(output_dir) / "color_records.jsonl"
    if not path.exists():
        return []

    pairs: list[tuple[MaterialRecord, ColorRecord]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        record = ColorRecord.model_validate_json(line)
        material = materials.get(record.material_id) or MaterialRecord(material_id=record.material_id)
        pairs.append((material, record))
    return pairs
