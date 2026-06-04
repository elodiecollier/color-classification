"""In-memory mock DB for the demo webapp.

Seeded at import time; mutations (tags, review resolutions) live in process
memory only — restarting the server resets the demo, which is a feature.
A real Directus-backed store replaces this at integration time via ports/.
"""

from __future__ import annotations

import itertools
from typing import Any

from core.models import ColorBucket

BUCKETS: list[str] = [b.value for b in ColorBucket]

# Query-term -> bucket synonyms for the search demo (CLAUDE.md §10):
# the acceptance demo is "green" returning sage / lime / forest swatches.
# (The real version would reuse the Gemini name-analysis; a static map is
# plenty for the demo and costs nothing.)
SYNONYMS: dict[str, str] = {
    "sage": "green", "lime": "green", "forest": "green", "olive": "green",
    "mint": "green",
    "navy": "blue", "sky": "blue", "teal": "blue", "azure": "blue",
    "crimson": "red", "scarlet": "red", "pink": "red", "rose": "red",
    "burgundy": "red",
    "rust": "orange", "amber": "orange", "tangerine": "orange",
    "gold": "yellow", "lemon": "yellow", "cream": "yellow",
    "violet": "purple", "lavender": "purple", "plum": "purple",
    "charcoal": "grey", "slate": "grey", "silver": "grey", "gray": "grey",
    "ivory": "white", "snow": "white",
    "ebony": "black", "onyx": "black",
    "tan": "brown", "beige": "brown", "walnut": "brown", "chocolate": "brown",
    "terracotta": "brown",
}

# Demo products: swatch colorway name + the product it belongs to.
# `hex` is for rendering swatch chips in the UI only. `tags` are color
# buckets (the §8 color_groups, simplified to plain strings for the demo).
# Note the demo narrative: "Fall River Glaze" sits untagged in the review
# queue (the motivating example), and "Driftwood" is untagged so a swatch
# can be classified live during the demo.
PRODUCTS: list[dict[str, Any]] = [
    {"id": 1, "name": "Sage Mist", "product": "Fiber Cement Siding", "company": "GreenBuild Co", "hex": "#9CAF88", "tags": ["green"]},
    {"id": 2, "name": "Fall River Glaze", "product": "Entry Door", "company": "Sun Mountain Door", "hex": "#B06A4A", "tags": []},
    {"id": 3, "name": "Arctic Frost", "product": "Vinyl Window", "company": "ClearView", "hex": "#F4F7F8", "tags": ["white"]},
    {"id": 4, "name": "Charcoal Slate", "product": "Composite Roofing", "company": "TopShield", "hex": "#3B3F42", "tags": ["grey", "black"]},
    {"id": 5, "name": "Terracotta Sun", "product": "Wall Cladding", "company": "EarthForm", "hex": "#C8704B", "tags": ["orange", "brown"]},
    {"id": 6, "name": "Navy Harbor", "product": "Metal Panel", "company": "SteelWorks", "hex": "#2C3E66", "tags": ["blue"]},
    {"id": 7, "name": "Lemon Zest", "product": "Accent Tile", "company": "BrightSpace", "hex": "#E8D44D", "tags": ["yellow"]},
    {"id": 8, "name": "Plum Twilight", "product": "Exterior Trim", "company": "ColorCraft", "hex": "#6E4A7E", "tags": ["purple"]},
    {"id": 9, "name": "Driftwood", "product": "Composite Decking", "company": "ShoreLine", "hex": "#A89F91", "tags": []},
    {"id": 10, "name": "Forest Canopy", "product": "Cedar Shingle", "company": "GreenBuild Co", "hex": "#3F6B4F", "tags": ["green"]},
]

# Ambiguous / conflicting classifications waiting for a human (§6 step 3).
# `suggested` carries the model's candidate buckets + a CSS color for the UI.
REVIEW_QUEUE: list[dict[str, Any]] = [
    {
        "id": 1,
        "product_id": 2,
        "reason": "Name 'Fall River Glaze' not an intuitive color (low confidence); "
                  "image clusters straddle the brown/orange boundary.",
        "suggested": [
            {"bucket": "brown", "css": "hsl(18 42% 42%)", "coverage": 0.58},
            {"bucket": "orange", "css": "hsl(22 55% 55%)", "coverage": 0.42},
        ],
    },
]

_review_ids = itertools.count(start=2)


def get_product(product_id: int) -> dict[str, Any] | None:
    return next((p for p in PRODUCTS if p["id"] == product_id), None)


def add_review_item(product_id: int, reason: str, suggested: list[dict[str, Any]]) -> dict[str, Any]:
    item = {"id": next(_review_ids), "product_id": product_id, "reason": reason, "suggested": suggested}
    REVIEW_QUEUE.append(item)
    return item
