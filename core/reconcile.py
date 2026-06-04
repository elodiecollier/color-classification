"""Reconcile the two independent signals: name vs image (CLAUDE.md §6).

Two independent signals cross-checked = trustworthy output. The rules:
  - AGREE (name buckets ∩ image buckets non-empty, per config policy)
      -> high confidence, source="reconciled".
  - CONFLICT (name says "blue", image says "grey")
      -> NEVER silently pick one. Flag needs_review=True, record a
        human-readable conflict_reason, keep both signals in the record.
        (Image stays authoritative for color_groups, but the record is
        routed to the review queue rather than trusted.)
  - IMAGE ONLY (no name, or name pre-check came back low-confidence)
      -> image result passes through, source="image".
  - NAME ONLY (no usable image)
      -> name result passes through, source="name"; confidence capped per
        config (names alone are the weakest signal).
  - NEITHER -> straight to review queue (product-image fallback is a
      deferred stretch goal, §15).

Pure function over NameAnalysisResult / ImageAnalysisResult (either may be
absent) -> the final ColorRecord (core/models.py §8 schema). All confidence
values and the agreement policy come from config/thresholds.py.

Will expose:
  - reconcile(record, name_result, image_result, config) -> ColorRecord
"""

from __future__ import annotations

from config.thresholds import DEFAULT, Thresholds
from core.models import (
    ColorRecord,
    ImageAnalysisResult,
    MaterialRecord,
    NameAnalysisResult,
)

def reconcile(
    record: MaterialRecord,
    name_result: NameAnalysisResult | None,
    image_result: ImageAnalysisResult | None,
    config: Thresholds = DEFAULT,
) -> ColorRecord:
    # TODO: narrow `config` to the ConfidenceThresholds section once it lands
    # in config/thresholds.py (it holds the name-confidence floor, the
    # agreement/conflict confidence values, and the needs_review cutoff).

    # nothing
    if not name_result and not image_result:
        return None
    
    if name_result.confidence < config.confidence:
        return 