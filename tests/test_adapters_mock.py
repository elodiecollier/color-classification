"""Tests for the adapters/mock data layer round-trip (§12)."""

from __future__ import annotations

import json

import pytest

from adapters.mock.file_color_sink import FileColorSink
from adapters.mock.fixture_record_source import FixtureRecordSource
from adapters.mock.local_image_store import LocalImageStore
from core.models import ClusterResult, ColorBucket, ColorRecord, HSL, MaterialRecord


# --- fixture_record_source --------------------------------------------------
def test_fixture_records_parse(tmp_path):
    p = tmp_path / "records.json"
    p.write_text(json.dumps([
        {"material_id": "m1", "swatch_name": "Sage", "image_ref": "x.png"},
        {"material_id": "m2"},
    ]))
    recs = list(FixtureRecordSource(p).iter_records())
    assert [r.material_id for r in recs] == ["m1", "m2"]
    assert recs[0].swatch_name == "Sage"
    assert recs[1].swatch_name is None and recs[1].image_ref is None


def test_malformed_fixture_fails_loudly(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps([{"swatch_name": "no id"}]))  # missing required material_id
    with pytest.raises(Exception):
        list(FixtureRecordSource(p).iter_records())


def test_real_fixture_parses():
    recs = list(FixtureRecordSource("fixtures/records.json").iter_records())
    assert len(recs) >= 5
    assert all(isinstance(r, MaterialRecord) for r in recs)


# --- local_image_store ------------------------------------------------------
def test_image_store_reads_existing(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG-fake")
    assert LocalImageStore(tmp_path).get_image("a.png") == b"\x89PNG-fake"


def test_image_store_missing_or_empty_ref_returns_none(tmp_path):
    store = LocalImageStore(tmp_path)
    assert store.get_image("nope.png") is None
    assert store.get_image("") is None


def test_image_store_reads_real_fixture_images():
    store = LocalImageStore("fixtures/images")
    assert store.get_image("sage_solid.png") is not None
    assert store.get_image("checkerboard.png") is not None


# --- file_color_sink --------------------------------------------------------
def _record(mid: str, *, needs_review: bool = False) -> ColorRecord:
    return ColorRecord(
        material_id=mid,
        source="image",
        color_groups=[ColorBucket.GREEN],
        canonical_hsl=HSL(h=120, s=0.4, l=0.5),
        lab_centroids=[ClusterResult(lab=(50.0, -40.0, 30.0), coverage=1.0)],
        coverage=1.0,
        confidence=0.9,
        needs_review=needs_review,
    )


def test_sink_routes_and_roundtrips(tmp_path):
    with FileColorSink(tmp_path) as sink:
        sink.write(_record("ok1"))
        sink.write(_record("review1", needs_review=True))
        sink.write(_record("ok2"))

    published = [
        ColorRecord.model_validate_json(line)
        for line in (tmp_path / "color_records.jsonl").read_text().splitlines()
    ]
    review = [
        ColorRecord.model_validate_json(line)
        for line in (tmp_path / "review_queue.jsonl").read_text().splitlines()
    ]
    assert [r.material_id for r in published] == ["ok1", "ok2"]
    assert [r.material_id for r in review] == ["review1"]
    # the nested dataclass centroid survives the JSONL round-trip
    assert published[0].lab_centroids[0].lab == (50.0, -40.0, 30.0)


def test_sink_truncates_on_open(tmp_path):
    FileColorSink(tmp_path).close()  # opening truncates
    with FileColorSink(tmp_path) as sink:
        sink.write(_record("only"))
    assert (tmp_path / "color_records.jsonl").read_text().count("\n") == 1


# --- integration: the data layer feeds the image pipeline -------------------
def test_data_layer_feeds_image_pipeline():
    from adapters.clustering.kmeans_sweep import KMeansSweep
    from adapters.clustering.preprocess import load_lab_pixels
    from core.image_pipeline import analyze_swatch

    recs = {r.material_id: r for r in FixtureRecordSource("fixtures/records.json").iter_records()}
    store = LocalImageStore("fixtures/images")
    img = store.get_image(recs["m1"].image_ref)  # Sage Mist -> sage_solid.png
    res = analyze_swatch(img, load_pixels=load_lab_pixels, strategy=KMeansSweep())
    assert res is not None and ColorBucket.GREEN in res.buckets
