"""Demo webapp data layer — a read-through view over the REAL pipeline data.

No hand-seeded demo data. Loaded at import time:
  - MATERIALS:      fixtures/records.json (the same MaterialRecords run_batch reads)
  - COLOR_RECORDS:  output/color_records.jsonl  — published §8 records, as written
                    by `uv run python -m cli.run_batch`
  - REVIEW_QUEUE:   output/review_queue.jsonl   — needs_review records

So the demo flow is: edit fixtures -> run the batch -> (re)start the webapp.
Admin mutations (tags, resolutions, live classify) are in-memory on top —
restart re-reads the files. A Directus-backed store replaces this via ports/.

Items are keyed by swatch (`swatch_id`, falling back to `material_id`), since a
material can have multiple swatches and each gets its own ColorRecord.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

from core.models import ColorBucket, ColorRecord, MaterialRecord, SearchResultItem

FIXTURES_PATH = Path("fixtures/records.json")
RECORDS_PATH = Path("output/color_records.jsonl")
REVIEW_PATH = Path("output/review_queue.jsonl")

BUCKETS: list[str] = [b.value for b in ColorBucket]


def key_of(material_id: str, swatch_id: str | None) -> str:
    """Unique per-swatch key — a material can have several swatches."""
    return swatch_id or material_id


def _load_materials() -> list[MaterialRecord]:
    if not FIXTURES_PATH.exists():
        return []
    return [MaterialRecord(**row) for row in json.loads(FIXTURES_PATH.read_text())]


def _load_jsonl(path: Path) -> list[ColorRecord]:
    if not path.exists():
        return []
    return [
        ColorRecord.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


MATERIALS: list[MaterialRecord] = _load_materials()

COLOR_RECORDS: dict[str, ColorRecord] = {
    key_of(r.material_id, r.swatch_id): r for r in _load_jsonl(RECORDS_PATH)
}

REVIEW_QUEUE: list[ColorRecord] = _load_jsonl(REVIEW_PATH)

# Swatches added live via the webapp ("Add to library") — in-memory only, like
# all admin mutations. Image bytes are kept here and served at /uploads/{key};
# everything is cleared on restart.
UPLOADED_IMAGES: dict[str, tuple[bytes, str]] = {}  # key -> (bytes, content type)
_upload_ids = itertools.count(1)


def add_uploaded_swatch(name: str, image_bytes: bytes, content_type: str) -> MaterialRecord:
    """Create a new in-memory material for a live-uploaded swatch image."""
    n = next(_upload_ids)
    material = MaterialRecord(
        material_id=f"upload-{n}",
        swatch_id=f"u{n}",
        swatch_name=name or None,
        company="(uploaded)",
    )
    MATERIALS.append(material)
    UPLOADED_IMAGES[key_of(material.material_id, material.swatch_id)] = (
        image_bytes,
        content_type or "image/png",
    )
    return material


# --- lookups -----------------------------------------------------------------


def get_material(item_id: str) -> MaterialRecord | None:
    """Look an item up by its swatch key (or bare material_id)."""
    return next(
        (m for m in MATERIALS
         if key_of(m.material_id, m.swatch_id) == item_id or m.material_id == item_id),
        None,
    )


def get_queued(item_id: str) -> ColorRecord | None:
    return next(
        (r for r in REVIEW_QUEUE if key_of(r.material_id, r.swatch_id) == item_id),
        None,
    )


def published_for(material: MaterialRecord) -> ColorRecord | None:
    return COLOR_RECORDS.get(key_of(material.material_id, material.swatch_id))


def find_record(material: MaterialRecord) -> ColorRecord | None:
    """Published record if any, else the queued (pending-review) one — what the
    admin view shows, and the candidate set for search. `rank_search` lets a
    pending-review record match by name/company text only, never by color, so an
    unconfirmed color classification never surfaces as a trustworthy result."""
    return published_for(material) or get_queued(key_of(material.material_id, material.swatch_id))


def _image_url(material: MaterialRecord) -> str | None:
    if material.image_ref:
        return f"/swatches/{material.image_ref}"  # fixture file (mock R2)
    if key_of(material.material_id, material.swatch_id) in UPLOADED_IMAGES:
        return f"/uploads/{key_of(material.material_id, material.swatch_id)}"
    return None


def to_search_item(material: MaterialRecord, record: ColorRecord | None) -> SearchResultItem:
    """The §10 join: ColorRecord + display fields from its MaterialRecord."""
    return SearchResultItem(
        material_id=material.material_id,
        swatch_id=material.swatch_id,
        swatch_name=material.swatch_name,
        company=material.company,
        image_url=_image_url(material),
        color_groups=record.color_groups if record else [],
        canonical_hsl=record.canonical_hsl if record else None,
        confidence=record.confidence if record else 0.0,
        needs_review=record.needs_review if record else False,
    )
