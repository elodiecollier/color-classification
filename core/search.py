"""Color search: term -> bucket -> matching swatches (CLAUDE.md §10).

The pure matcher over already-loaded (MaterialRecord, ColorRecord) pairs — no
I/O, so it lives in core/. The loader that reads run_batch's output lives in
`adapters/mock/jsonl_color_source.py`. One search implementation that both the
webapp and any CLI can call.

term -> bucket via an exact bucket name or the synonym map (e.g. "sage" -> green);
then return the published records whose `color_groups` include that bucket, as a
`SearchResponse` of `SearchResultItem`s (the §10 contract).
"""

from __future__ import annotations

from collections.abc import Iterable

from core.models import (
    ColorBucket,
    ColorRecord,
    MaterialRecord,
    SearchResponse,
    SearchResultItem,
)

# Query-term -> bucket synonyms (the §10 demo: "green" returns sage/lime/forest).
# Canonical home for these; the webapp can import this instead of its own copy.
DEFAULT_SYNONYMS: dict[str, ColorBucket] = {
    "sage": ColorBucket.GREEN, "lime": ColorBucket.GREEN, "forest": ColorBucket.GREEN,
    "olive": ColorBucket.GREEN, "mint": ColorBucket.GREEN,
    "navy": ColorBucket.BLUE, "sky": ColorBucket.BLUE, "teal": ColorBucket.BLUE,
    "azure": ColorBucket.BLUE,
    "crimson": ColorBucket.RED, "scarlet": ColorBucket.RED, "pink": ColorBucket.RED,
    "rose": ColorBucket.RED, "burgundy": ColorBucket.RED,
    "rust": ColorBucket.ORANGE, "amber": ColorBucket.ORANGE, "tangerine": ColorBucket.ORANGE,
    "gold": ColorBucket.YELLOW, "lemon": ColorBucket.YELLOW, "cream": ColorBucket.YELLOW,
    "violet": ColorBucket.PURPLE, "lavender": ColorBucket.PURPLE, "plum": ColorBucket.PURPLE,
    "charcoal": ColorBucket.GREY, "slate": ColorBucket.GREY, "silver": ColorBucket.GREY,
    "gray": ColorBucket.GREY,
    "ivory": ColorBucket.WHITE, "snow": ColorBucket.WHITE,
    "ebony": ColorBucket.BLACK, "onyx": ColorBucket.BLACK,
    "tan": ColorBucket.BROWN, "beige": ColorBucket.BROWN, "walnut": ColorBucket.BROWN,
    "chocolate": ColorBucket.BROWN, "terracotta": ColorBucket.BROWN,
}


def resolve_bucket(
    term: str, synonyms: dict[str, ColorBucket] = DEFAULT_SYNONYMS
) -> ColorBucket | None:
    """Map a query term to a bucket: an exact bucket name, else the synonym map."""
    cleaned = term.strip().lower()
    if not cleaned:
        return None
    try:
        return ColorBucket(cleaned)
    except ValueError:
        return synonyms.get(cleaned)


def search(
    term: str,
    pairs: Iterable[tuple[MaterialRecord, ColorRecord]],
    *,
    synonyms: dict[str, ColorBucket] = DEFAULT_SYNONYMS,
) -> SearchResponse:
    """Return the swatches whose color_groups include the term's bucket.

    `pairs` are (MaterialRecord, ColorRecord) — the published records joined with
    their source rows for display fields. An unmapped term -> bucket=None, zero
    results (no fuzzy fallback, per §10). `needs_review` records are skipped
    defensively (search surfaces trustworthy results only).
    """
    bucket = resolve_bucket(term, synonyms)
    results: list[SearchResultItem] = []
    if bucket is not None:
        results = [
            _to_item(material, record)
            for material, record in pairs
            if not record.needs_review and bucket in record.color_groups
        ]
    return SearchResponse(query=term, bucket=bucket, count=len(results), results=results)


def _to_item(material: MaterialRecord, record: ColorRecord) -> SearchResultItem:
    """The §10 join: ColorRecord + display fields from its MaterialRecord."""
    return SearchResultItem(
        material_id=material.material_id,
        swatch_id=material.swatch_id,
        swatch_name=material.swatch_name,
        company=material.company,
        image_url=None,  # no hosted swatch images in the mock; UI uses canonical_hsl
        color_groups=record.color_groups,
        canonical_hsl=record.canonical_hsl,
        confidence=record.confidence,
        needs_review=record.needs_review,
    )
