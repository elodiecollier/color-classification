"""In-memory mock DB for the demo webapp — ON the core/models.py contract.

Mirrors the real system's split (CLAUDE.md §12):
  - MATERIALS:      MaterialRecord rows (what Directus holds).
  - COLOR_RECORDS:  published §8 ColorRecords keyed by material_id (the color
                    sink). Search reads ONLY from here.
  - REVIEW_QUEUE:   ColorRecords with needs_review=True, NOT yet published —
                    resolving one publishes it.

Mutations live in process memory; restarting the server resets the demo.
A Directus-backed store replaces this at integration time via ports/.
"""

from __future__ import annotations

import colorsys

from core.models import (
    ClusterResult,
    ColorBucket,
    ColorRecord,
    HSL,
    MaterialRecord,
    SearchResultItem,
)

BUCKETS: list[str] = [b.value for b in ColorBucket]

# Query-term -> bucket synonyms for the search demo (§10: "map the user's color
# term -> bucket"). The real version reuses Gemini name-analysis; a static map
# is plenty for the demo.
SYNONYMS: dict[str, ColorBucket] = {
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


def _hsl(hex_str: str) -> HSL:
    """'#RRGGBB' -> HSL, for seeding canonical_hsl (UI renders chips from it)."""
    r, g, b = (int(hex_str[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    return HSL(h=h * 360, s=s, l=lightness)


# Demo seed: (material_id, swatch_id, swatch_name, company, display hex,
# published color_groups — None = not yet classified).
# Narrative: 'Fall River Glaze' (m2) sits in the review queue; 'Driftwood' (m9)
# is fully unclassified so a swatch can be classified live during the demo.
_SEED: list[tuple[str, str, str, str, str, list[ColorBucket] | None]] = [
    ("m1", "s1", "Sage Mist", "GreenBuild Co", "#9CAF88", [ColorBucket.GREEN]),
    ("m2", "s2", "Fall River Glaze", "Sun Mountain Door", "#B06A4A", None),
    ("m3", "s3", "Arctic Frost", "ClearView", "#F4F7F8", [ColorBucket.WHITE]),
    ("m4", "s4", "Charcoal Slate", "TopShield", "#3B3F42", [ColorBucket.GREY, ColorBucket.BLACK]),
    ("m5", "s5", "Terracotta Sun", "EarthForm", "#C8704B", [ColorBucket.ORANGE, ColorBucket.BROWN]),
    ("m6", "s6", "Navy Harbor", "SteelWorks", "#2C3E66", [ColorBucket.BLUE]),
    ("m7", "s7", "Lemon Zest", "BrightSpace", "#E8D44D", [ColorBucket.YELLOW]),
    ("m8", "s8", "Plum Twilight", "ColorCraft", "#6E4A7E", [ColorBucket.PURPLE]),
    ("m9", "s9", "Driftwood", "ShoreLine", "#A89F91", None),
    ("m10", "s10", "Forest Canopy", "GreenBuild Co", "#3F6B4F", [ColorBucket.GREEN]),
]

MATERIALS: list[MaterialRecord] = [
    MaterialRecord(material_id=mid, swatch_id=sid, swatch_name=name, company=company)
    for mid, sid, name, company, _hex, _groups in _SEED
]

COLOR_RECORDS: dict[str, ColorRecord] = {
    mid: ColorRecord(
        material_id=mid,
        swatch_id=sid,
        source="manual",
        color_groups=groups,
        canonical_hsl=_hsl(hex_str),
        confidence=0.95,
    )
    for mid, sid, _name, _company, hex_str, groups in _SEED
    if groups is not None
}

# 'Fall River Glaze': name vs image conflicted (§6 step 3) -> flagged, queued,
# NOT published. The candidate buckets + raw centroids ride on the record.
REVIEW_QUEUE: list[ColorRecord] = [
    ColorRecord(
        material_id="m2",
        swatch_id="s2",
        source="reconciled",
        color_groups=[ColorBucket.BROWN, ColorBucket.ORANGE],
        canonical_hsl=_hsl("#B06A4A"),
        lab_centroids=[
            ClusterResult(lab=(45.0, 18.0, 26.0), coverage=0.58),
            ClusterResult(lab=(58.0, 25.0, 38.0), coverage=0.42),
        ],
        coverage=1.0,
        confidence=0.45,
        needs_review=True,
        conflict_reason="Name 'Fall River Glaze' not an intuitive color (low "
                        "confidence); image clusters straddle the brown/orange boundary.",
    ),
]


# --- lookups -----------------------------------------------------------------


def get_material(material_id: str) -> MaterialRecord | None:
    return next((m for m in MATERIALS if m.material_id == material_id), None)


def get_queued(material_id: str) -> ColorRecord | None:
    return next((r for r in REVIEW_QUEUE if r.material_id == material_id), None)


def find_record(material_id: str) -> ColorRecord | None:
    """Published record if any, else the queued (pending-review) one — what the
    admin view shows. Search must use COLOR_RECORDS only."""
    return COLOR_RECORDS.get(material_id) or get_queued(material_id)


def to_search_item(material: MaterialRecord, record: ColorRecord | None) -> SearchResultItem:
    """The §10 join: ColorRecord + display fields from its MaterialRecord."""
    return SearchResultItem(
        material_id=material.material_id,
        swatch_id=material.swatch_id,
        swatch_name=material.swatch_name,
        company=material.company,
        image_url=None,  # no hosted swatch images in the mock; UI uses canonical_hsl
        color_groups=record.color_groups if record else [],
        canonical_hsl=record.canonical_hsl if record else None,
        confidence=record.confidence if record else 0.0,
        needs_review=record.needs_review if record else False,
    )
