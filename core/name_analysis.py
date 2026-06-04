"""Swatch NAME -> bucket(s) + confidence (CLAUDE.md §6 step 1, §9).

Gemini handles LANGUAGE only — "is this name intuitively a color?". Descriptive
names ("Sage" -> green) resolve with high confidence; opaque marketing names
("Fall River Glaze") come back with low confidence and/or no buckets, and the
flow falls through to the (authoritative) image pipeline.

Pure logic: build the prompt, call an INJECTED `ports.llm.LLMClient`, then parse
+ validate against the fixed 10 buckets. No SDK import here -> unit-testable with
a fake client (no API key). Defensive per §9: a parse failure or out-of-taxonomy
output is never fatal — it just yields no/low signal.

Semantics: an empty `buckets` means "no usable color from the name" regardless of
confidence; callers (reconcile) should fall through to the image in that case.
The confidence is compared to `config.confidence.name_intuitive_floor`
downstream — not here.
"""

from __future__ import annotations

import json

from core.models import ColorBucket, NameAnalysisResult
from ports.llm import LLMClient

_ALLOWED = ", ".join(b.value for b in ColorBucket)

_SYSTEM = (
    "You map a building-product color NAME to standard color buckets.\n"
    f"Allowed buckets (use ONLY these exact words): {_ALLOWED}.\n"
    "A name may map to one or more buckets, or to none if it does not "
    "intuitively convey a color.\n"
    'Respond with STRICT JSON only: {"buckets": ["<bucket>", ...], '
    '"confidence": <number 0..1>}.\n'
    "- buckets: only values from the allowed list; use [] when the name conveys "
    "no intuitive color.\n"
    "- confidence: your certainty that the name intuitively denotes those colors. "
    'Descriptive names ("Sage", "Forest Green") -> high; opaque marketing names '
    '("Fall River Glaze") -> low.\n'
    "No prose — a JSON object only."
)


def analyze_name(
    name: str | None,
    client: LLMClient,
    *,
    company: str | None = None,
) -> NameAnalysisResult:
    """Classify a swatch name into color buckets + a confidence (0-1)."""
    cleaned = (name or "").strip()
    if not cleaned:
        return NameAnalysisResult(buckets=[], confidence=0.0)

    user = f"Color name: {cleaned!r}"
    if company:
        user += f"\nManufacturer: {company}"

    try:
        raw = client.complete_json(system=_SYSTEM, user=user)
        data = json.loads(raw)
    except Exception:
        # transport error or non-JSON output -> no usable signal (§9)
        return NameAnalysisResult(buckets=[], confidence=0.0)

    return NameAnalysisResult(
        buckets=_validate_buckets(data.get("buckets")),
        confidence=_clamp01(data.get("confidence")),
    )


def _validate_buckets(raw: object) -> list[ColorBucket]:
    """Keep only valid, deduped buckets; silently drop anything out-of-taxonomy."""
    if not isinstance(raw, list):
        return []
    out: list[ColorBucket] = []
    for value in raw:
        try:
            bucket = ColorBucket(str(value).strip().lower())
        except ValueError:
            continue
        if bucket not in out:
            out.append(bucket)
    return out


def _clamp01(raw: object) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return min(max(value, 0.0), 1.0)
