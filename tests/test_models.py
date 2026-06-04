"""Smoke tests for the shared record schema (Step 0).

No logic — just guards that every record the lanes depend on constructs and
validates, and that frozen models reject mutation. Catches schema typos early.
"""

from __future__ import annotations

import pytest

from core.models import (
    ClusterResult,
    ColorBucket,
    ColorRecord,
    HSL,
    ImageAnalysisResult,
    MaterialRecord,
    NameAnalysisResult,
    SearchResponse,
    SearchResultItem,
)


def test_material_record_minimal():
    r = MaterialRecord(material_id="m1")
    assert r.swatch_name is None and r.image_ref is None


def test_name_analysis_result():
    r = NameAnalysisResult(buckets=[ColorBucket.GREEN], confidence=0.9)
    assert r.buckets == [ColorBucket.GREEN]


def test_image_analysis_result():
    r = ImageAnalysisResult(
        buckets=[ColorBucket.BLUE],
        centroids=[ClusterResult(lab=(32.3, 79.2, -107.9), coverage=1.0)],
        canonical_hsl=HSL(h=240, s=1.0, l=0.5),
    )
    assert r.centroids[0].coverage == 1.0


def test_color_record_full():
    rec = ColorRecord(
        material_id="m1",
        swatch_id="s1",
        source="reconciled",
        color_groups=[ColorBucket.GREEN],
        canonical_hsl=HSL(h=120, s=0.6, l=0.4),
        lab_centroids=[ClusterResult(lab=(50.0, -40.0, 30.0), coverage=0.8)],
        coverage=0.8,
        confidence=0.95,
    )
    assert rec.source == "reconciled"
    assert rec.lab_centroids[0].lab == (50.0, -40.0, 30.0)


def test_color_record_name_only_defaults():
    rec = ColorRecord(
        material_id="m2", source="name", color_groups=[ColorBucket.RED], confidence=0.7
    )
    assert rec.lab_centroids == [] and rec.canonical_hsl is None and rec.coverage is None


def test_search_response_view():
    resp = SearchResponse(
        query="green",
        bucket=ColorBucket.GREEN,
        count=1,
        results=[
            SearchResultItem(
                material_id="m1",
                swatch_name="Sage",
                company="Acme",
                color_groups=[ColorBucket.GREEN],
                confidence=0.9,
            )
        ],
    )
    assert resp.count == 1 and resp.results[0].swatch_name == "Sage"


def test_records_are_frozen():
    rec = ColorRecord(
        material_id="m1", source="name", color_groups=[ColorBucket.RED], confidence=0.5
    )
    with pytest.raises(Exception):
        rec.material_id = "x"  # type: ignore[misc]
