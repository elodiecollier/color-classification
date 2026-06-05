"""Tests for core/reconcile.py — the §6 decision table, exhaustively.

One test per row of the matrix (agree / conflict / image-only / name-only /
neither), plus the invariants: lab_centroids always survive when an image
result exists, and review-queue records are ColorRecords — never None.
All synthetic; no LLM, no images.
"""

from __future__ import annotations

import pytest

from config.thresholds import DEFAULT
from core.models import (
    ClusterResult,
    ColorBucket,
    HSL,
    ImageAnalysisResult,
    MaterialRecord,
    NameAnalysisResult,
    VisionAnalysisResult,
)
from core.reconcile import reconcile

B = ColorBucket
CFG = DEFAULT.confidence

RECORD = MaterialRecord(
    material_id="m1", swatch_id="s1", swatch_name="Fall River Glaze", company="Acme"
)

CENTROIDS = [
    ClusterResult(lab=(45.0, 18.0, 26.0), coverage=0.6),
    ClusterResult(lab=(58.0, 25.0, 38.0), coverage=0.4),
]


def name(buckets, confidence):
    return NameAnalysisResult(buckets=buckets, confidence=confidence)


def image(buckets, centroids=CENTROIDS):
    return ImageAnalysisResult(
        buckets=buckets, centroids=centroids, canonical_hsl=HSL(h=20.0, s=0.5, l=0.4)
    )


# --- the decision table ------------------------------------------------------


def test_agree_is_high_confidence_reconciled():
    rec = reconcile(RECORD, name([B.BROWN], 0.9), image([B.BROWN, B.ORANGE]))
    assert rec.source == "reconciled"
    assert rec.color_groups == [B.BROWN, B.ORANGE]  # image ordering, authoritative
    assert rec.confidence == CFG.agreement_confidence
    assert rec.needs_review is False
    assert rec.conflict_reason is None


def test_conflict_flags_review_and_never_silently_picks():
    rec = reconcile(RECORD, name([B.BLUE], 0.9), image([B.GREY]))
    assert rec.needs_review is True
    assert rec.confidence == CFG.conflict_confidence
    assert rec.color_groups == [B.GREY]  # image kept, but flagged — not trusted
    assert "blue" in rec.conflict_reason and "grey" in rec.conflict_reason
    assert "Fall River Glaze" in rec.conflict_reason


def test_image_only_passes_through():
    rec = reconcile(RECORD, None, image([B.BROWN]))
    assert rec.source == "image"
    assert rec.color_groups == [B.BROWN]
    assert rec.confidence == CFG.image_only_confidence


def test_low_confidence_name_falls_through_to_image():
    # name exists but is below the intuitive floor -> image-only path, no conflict
    rec = reconcile(RECORD, name([B.BLUE], CFG.name_intuitive_floor - 0.1), image([B.GREY]))
    assert rec.source == "image"
    assert rec.needs_review is False
    assert rec.conflict_reason is None


def test_name_with_empty_buckets_is_unusable():
    rec = reconcile(RECORD, name([], 0.99), image([B.GREY]))
    assert rec.source == "image"


def test_name_only_is_capped():
    rec = reconcile(RECORD, name([B.GREEN], 0.95), None)
    assert rec.source == "name"
    assert rec.color_groups == [B.GREEN]
    assert rec.confidence == CFG.name_only_cap  # 0.95 capped down
    assert rec.lab_centroids == [] and rec.coverage is None  # no image artifacts


def test_neither_signal_is_a_review_record_not_none():
    rec = reconcile(RECORD, None, None)
    assert rec is not None
    assert rec.needs_review is True
    assert rec.confidence == 0.0
    assert rec.color_groups == []
    assert rec.material_id == "m1" and rec.swatch_id == "s1"


# --- invariants ---------------------------------------------------------------


@pytest.mark.parametrize(
    "name_result",
    [None, name([B.BROWN], 0.9), name([B.BLUE], 0.9)],  # image-only, agree, conflict
)
def test_image_artifacts_always_survive(name_result):
    """lab_centroids are the durable §8 asset — kept on EVERY image branch,
    including conflicts."""
    rec = reconcile(RECORD, name_result, image([B.BROWN]))
    assert rec.lab_centroids == CENTROIDS
    assert rec.canonical_hsl is not None
    assert rec.coverage == pytest.approx(1.0)


def test_empty_image_buckets_is_unusable_image():
    # an image result with no surviving buckets must not count as a signal
    rec = reconcile(RECORD, name([B.GREEN], 0.9), image([], centroids=[]))
    assert rec.source == "name"


# --- vision third-opinion tiebreak (§3 amendment) ----------------------------


def vision(buckets, confidence=0.85):
    return VisionAnalysisResult(buckets=buckets, confidence=confidence)


def test_vision_siding_with_image_breaks_the_conflict():
    rec = reconcile(
        RECORD, name([B.BLUE], 0.9), image([B.GREY]),
        vision_result=vision([B.GREY]),
    )
    assert rec.needs_review is False
    assert rec.conflict_reason is None
    assert rec.color_groups == [B.GREY]
    assert rec.confidence == CFG.vision_tiebreak_confidence
    assert rec.lab_centroids == CENTROIDS  # evidence still rides along


def test_vision_siding_with_name_stays_in_review_with_richer_reason():
    rec = reconcile(
        RECORD, name([B.BLUE], 0.9), image([B.GREY]),
        vision_result=vision([B.BLUE]),
    )
    assert rec.needs_review is True
    assert "sided with the NAME" in rec.conflict_reason


def test_vision_matching_neither_stays_in_review():
    rec = reconcile(
        RECORD, name([B.BLUE], 0.9), image([B.GREY]),
        vision_result=vision([B.RED]),
    )
    assert rec.needs_review is True
    assert "matched neither" in rec.conflict_reason


def test_empty_vision_changes_nothing():
    with_v = reconcile(
        RECORD, name([B.BLUE], 0.9), image([B.GREY]),
        vision_result=vision([], confidence=0.0),
    )
    without = reconcile(RECORD, name([B.BLUE], 0.9), image([B.GREY]))
    assert with_v == without


def test_vision_is_ignored_when_signals_agree():
    # vision is a CONFLICT tiebreak only — agreement doesn't consult it
    rec = reconcile(
        RECORD, name([B.BROWN], 0.9), image([B.BROWN]),
        vision_result=vision([B.RED]),
    )
    assert rec.confidence == CFG.agreement_confidence
    assert rec.needs_review is False
