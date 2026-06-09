"""Color search: term -> matching swatches, ranked (CLAUDE.md §10).

The pure matcher over already-loaded (MaterialRecord, ColorRecord) pairs — no
I/O, so it lives in core/. The loader that reads run_batch's output lives in
`adapters/mock/jsonl_color_source.py`. One search/ranking implementation
(`rank_search`) that both the webapp and any CLI call.

A term matches a swatch two ways, and results are ranked by both:
  - COLOR match: the term resolves to a bucket (an exact bucket name or a
    synonym, e.g. "sage"/"navy" -> green/blue) and that bucket is in the
    swatch's `color_groups`.
  - STRING match: the term appears in the swatch *name* or *company*. This
    surfaces swatches whose name names the color even when the pixels were
    classified elsewhere (e.g. "Navy/Ivory" classified white, not blue).

Ranking (best color match, then string match; both = top):
  1. swatches matching BOTH color and string rank highest,
  2. then color matches, ordered by confidence,
  3. then string-only matches, ordered by how well the term hits the name.
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
    # green
    "sage": ColorBucket.GREEN, "lime": ColorBucket.GREEN, "forest": ColorBucket.GREEN,
    "olive": ColorBucket.GREEN, "mint": ColorBucket.GREEN, "avocado": ColorBucket.GREEN,
    # blue
    "navy": ColorBucket.BLUE, "sky": ColorBucket.BLUE, "teal": ColorBucket.BLUE,
    "azure": ColorBucket.BLUE, "sapphire": ColorBucket.BLUE,
    # red
    "crimson": ColorBucket.RED, "scarlet": ColorBucket.RED, "pink": ColorBucket.RED,
    "rose": ColorBucket.RED, "burgundy": ColorBucket.RED,
    # orange
    "rust": ColorBucket.ORANGE, "amber": ColorBucket.ORANGE, "tangerine": ColorBucket.ORANGE,
    "spice": ColorBucket.ORANGE,
    # yellow
    "gold": ColorBucket.YELLOW, "lemon": ColorBucket.YELLOW, "cream": ColorBucket.YELLOW,
    # purple
    "violet": ColorBucket.PURPLE, "lavender": ColorBucket.PURPLE, "plum": ColorBucket.PURPLE,
    # grey
    "charcoal": ColorBucket.GREY, "slate": ColorBucket.GREY, "silver": ColorBucket.GREY,
    "gray": ColorBucket.GREY, "pebble": ColorBucket.GREY, "ash": ColorBucket.GREY,
    # white
    "ivory": ColorBucket.WHITE, "snow": ColorBucket.WHITE,
    # black
    "ebony": ColorBucket.BLACK, "onyx": ColorBucket.BLACK, "midnight": ColorBucket.BLACK,
    # brown
    "tan": ColorBucket.BROWN, "beige": ColorBucket.BROWN, "walnut": ColorBucket.BROWN,
    "chocolate": ColorBucket.BROWN, "terracotta": ColorBucket.BROWN,
    "teak": ColorBucket.BROWN, "timber": ColorBucket.BROWN,
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


def _string_relevance(term: str, material: MaterialRecord) -> int:
    """How strongly `term` (already lowercased) hits the swatch's text fields.
    Higher = more relevant: exact name > name prefix > name substring > company.
    0 means no string match."""
    name = (material.swatch_name or "").lower()
    company = (material.company or "").lower()
    if term and term == name:
        return 4
    if term and name.startswith(term):
        return 3
    if term and term in name:
        return 2
    if term and term in company:
        return 1
    return 0


def rank_search(
    term: str,
    pairs: Iterable[tuple[MaterialRecord, ColorRecord]],
    *,
    synonyms: dict[str, ColorBucket] = DEFAULT_SYNONYMS,
) -> tuple[ColorBucket | None, list[tuple[MaterialRecord, ColorRecord]]]:
    """Resolve the term and return (bucket, matched pairs ordered by relevance).

    `pairs` are (MaterialRecord, ColorRecord) — records joined with their source
    rows. A pair matches if the term's bucket is in its `color_groups` (COLOR
    match) and/or the term hits its name/company (STRING match). Ordering:
    both-matches first, then color matches by confidence, then string-only
    matches by name relevance; ties break on name for determinism.

    `needs_review` records match by STRING only — never by color: an unconfirmed
    color classification must not surface as a trustworthy color result, but the
    swatch is still findable by the name/company text the user typed (the result
    carries its `needs_review` flag so the UI can badge it).
    """
    cleaned = term.strip().lower()
    bucket = resolve_bucket(cleaned, synonyms)

    def color_matches(record: ColorRecord) -> bool:
        return bucket is not None and not record.needs_review and bucket in record.color_groups

    matched: list[tuple[MaterialRecord, ColorRecord]] = []
    for material, record in pairs:
        if color_matches(record) or _string_relevance(cleaned, material):
            matched.append((material, record))

    def score(mr: tuple[MaterialRecord, ColorRecord]) -> tuple[int, float, int]:
        material, record = mr
        color_match = color_matches(record)
        string_rel = _string_relevance(cleaned, material)
        return (
            1 if (color_match and string_rel) else 0,   # both -> top tier
            record.confidence if color_match else 0.0,   # then best color match
            string_rel,                                   # then string relevance
        )

    # Name-ascending base order, then a stable descending sort by score: equal
    # scores keep the name order, so results are fully deterministic.
    matched.sort(key=lambda mr: (mr[0].swatch_name or mr[0].material_id).lower())
    matched.sort(key=score, reverse=True)
    return bucket, matched


def search(
    term: str,
    pairs: Iterable[tuple[MaterialRecord, ColorRecord]],
    *,
    synonyms: dict[str, ColorBucket] = DEFAULT_SYNONYMS,
) -> SearchResponse:
    """Ranked color + name/company search over `pairs` (see `rank_search`).

    `pairs` are (MaterialRecord, ColorRecord) — the published records joined with
    their source rows for display fields. `needs_review` records are skipped
    defensively (search surfaces trustworthy results only).
    """
    bucket, matched = rank_search(term, pairs, synonyms=synonyms)
    results = [_to_item(material, record) for material, record in matched]
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
