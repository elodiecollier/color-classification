"""Gemini-vision third opinion on a swatch IMAGE (CLAUDE.md §3 amendment).

ADVISORY ONLY. The deterministic clustering pipeline remains the authoritative
color MEASUREMENT (it alone produces centroids/coverage, and eyeballing LLMs
average a checkerboard into grey). This signal exists to break name-vs-image
CONFLICTS in reconcile: when the two primary signals disagree, a third
independent reader votes — siding with the image publishes it (tiebreak
confidence), siding with the name keeps the record in review with a richer
reason.

Same defensive contract as name_analysis (§9): strict-JSON prompt, taxonomy
validation, parse failure -> no signal. The client is injected
(`ports.llm.VisionLLMClient`) so this stays SDK-free and fake-testable.
"""

from __future__ import annotations

import json

from core.models import ColorBucket, VisionAnalysisResult
from core.name_analysis import _clamp01, _validate_buckets
from ports.llm import VisionLLMClient

_ALLOWED = ", ".join(b.value for b in ColorBucket)

_SYSTEM = (
    "You judge the dominant color(s) of a building-product swatch IMAGE.\n"
    f"Allowed buckets (use ONLY these exact words): {_ALLOWED}.\n"
    "Report every clearly-present dominant color (a two-tone swatch has two), "
    "ignoring shadows, glare, and borders. A black-and-white checkerboard is "
    "black AND white — never grey.\n"
    'Respond with STRICT JSON only: {"buckets": ["<bucket>", ...], '
    '"confidence": <number 0..1>}.\n'
    "No prose — a JSON object only."
)


def analyze_image_vision(
    image_bytes: bytes,
    client: VisionLLMClient,
    *,
    mime_type: str = "image/png",
) -> VisionAnalysisResult:
    """Ask the vision model which buckets it sees. Defensive: any failure or
    out-of-taxonomy output degrades to an empty, zero-confidence result."""
    try:
        raw = client.complete_json_vision(
            system=_SYSTEM,
            user="Which color buckets describe this swatch?",
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        data = json.loads(raw)
    except Exception:
        return VisionAnalysisResult(buckets=[], confidence=0.0)

    return VisionAnalysisResult(
        buckets=_validate_buckets(data.get("buckets")),
        confidence=_clamp01(data.get("confidence")),
    )
