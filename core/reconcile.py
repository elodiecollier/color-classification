"""Reconcile the two independent signals: name vs image (CLAUDE.md §6).

Two independent signals cross-checked = trustworthy output. The rules:
  - AGREE (name buckets ∩ image buckets non-empty)
      -> high confidence, source="reconciled".
  - CONFLICT (name says "blue", image says "grey")
      -> NEVER silently pick one. Flag needs_review=True, record a
        human-readable conflict_reason. Image stays authoritative for
        color_groups, but the record routes to the review queue.
  - IMAGE ONLY (no name, or name pre-check below the intuitive floor)
      -> image result passes through, source="image".
  - NAME ONLY (no usable image)
      -> name result passes through, source="name"; confidence capped
        (names alone are the weakest signal).
  - NEITHER -> a needs_review record (the review queue IS records with
      needs_review=True — never None; product-image fallback is deferred, §15).

Pure function: every confidence value and the name floor come from
config/thresholds.py (ConfidenceThresholds). Image-derived artifacts
(canonical_hsl, lab_centroids, coverage) ride along on EVERY branch where an
image result exists — including conflicts; centroids are the durable §8 asset.
"""

from __future__ import annotations

from config.thresholds import DEFAULT, Thresholds
from core.models import (
    ColorBucket,
    ColorRecord,
    ImageAnalysisResult,
    MaterialRecord,
    NameAnalysisResult,
    Source,
)


def reconcile(
    record: MaterialRecord,
    name_result: NameAnalysisResult | None,
    image_result: ImageAnalysisResult | None,
    config: Thresholds = DEFAULT,
) -> ColorRecord:
    """Merge the (optional) name and image signals into the final ColorRecord."""
    cfg = config.confidence

    # Normalize each signal to "usable or not" ONCE — a signal can exist yet
    # carry nothing useful (empty buckets, or a name below the intuitive floor).
    name_ok = (
        name_result is not None
        and bool(name_result.buckets)
        and name_result.confidence >= cfg.name_intuitive_floor
    )
    image_ok = image_result is not None and bool(image_result.buckets)

    match (name_ok, image_ok):
        case (False, False):
            # NEITHER: nothing trustworthy -> review queue.
            return _build(
                record, source="reconciled", color_groups=[],
                confidence=0.0, needs_review=True,
            )

        case (True, False):
            # NAME ONLY: pass through, capped — the weakest signal alone.
            assert name_result is not None  # for the type checker; name_ok implies it
            confidence = min(name_result.confidence, cfg.name_only_cap)
            return _build(
                record, source="name", color_groups=list(name_result.buckets),
                confidence=confidence,
                needs_review=confidence < cfg.needs_review_below,
            )

        case (False, True):
            # IMAGE ONLY (incl. name below the floor): authoritative pass-through.
            assert image_result is not None
            return _build(
                record, source="image", color_groups=list(image_result.buckets),
                confidence=cfg.image_only_confidence, image_result=image_result,
                needs_review=cfg.image_only_confidence < cfg.needs_review_below,
            )

        case _:
            # BOTH usable: agree or conflict (§6 step 3).
            assert name_result is not None and image_result is not None
            agree = bool(set(name_result.buckets) & set(image_result.buckets))
            if agree:
                return _build(
                    record, source="reconciled",
                    color_groups=list(image_result.buckets),  # image ordering is authoritative
                    confidence=cfg.agreement_confidence, image_result=image_result,
                    needs_review=cfg.agreement_confidence < cfg.needs_review_below,
                )
            return _build(
                record, source="reconciled",
                color_groups=list(image_result.buckets),  # image kept, but NOT trusted silently
                confidence=cfg.conflict_confidence, image_result=image_result,
                needs_review=True,
                conflict_reason=(
                    f"Name {record.swatch_name!r} suggested "
                    f"[{_names(name_result.buckets)}] but the image found "
                    f"[{_names(image_result.buckets)}] — no overlap."
                ),
            )


def _build(
    record: MaterialRecord,
    *,
    source: Source,
    color_groups: list[ColorBucket],
    confidence: float,
    image_result: ImageAnalysisResult | None = None,
    needs_review: bool = False,
    conflict_reason: str | None = None,
) -> ColorRecord:
    """Assemble the §8 record; image artifacts ride along whenever they exist."""
    coverage = None
    if image_result is not None and image_result.centroids:
        coverage = round(min(sum(c.coverage for c in image_result.centroids), 1.0), 3)
    return ColorRecord(
        material_id=record.material_id,
        swatch_id=record.swatch_id,
        source=source,
        color_groups=color_groups,
        canonical_hsl=image_result.canonical_hsl if image_result else None,
        lab_centroids=list(image_result.centroids) if image_result else [],
        coverage=coverage,
        confidence=confidence,
        needs_review=needs_review,
        conflict_reason=conflict_reason,
    )


def _names(buckets: list[ColorBucket]) -> str:
    return ", ".join(b.value for b in buckets)
