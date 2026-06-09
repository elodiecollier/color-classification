"""Tests for core/search + the JSONL loader (CLAUDE.md §10)."""

from __future__ import annotations

from adapters.mock.file_color_sink import FileColorSink
from adapters.mock.jsonl_color_source import load_classified
from core.models import ColorBucket, ColorRecord, HSL, MaterialRecord
from core.search import DEFAULT_SYNONYMS, resolve_bucket, search

B = ColorBucket


def _pair(mid, buckets, *, name=None, company=None, confidence=0.9, needs_review=False):
    material = MaterialRecord(material_id=mid, swatch_name=name, company=company)
    record = ColorRecord(
        material_id=mid, source="image", color_groups=buckets,
        canonical_hsl=HSL(h=120, s=0.4, l=0.5), confidence=confidence, needs_review=needs_review,
    )
    return material, record


# --- resolve_bucket ---------------------------------------------------------
def test_resolve_exact_bucket_name():
    assert resolve_bucket("green") == B.GREEN
    assert resolve_bucket("  GREEN ") == B.GREEN  # trimmed + case-insensitive


def test_resolve_synonym():
    assert resolve_bucket("sage") == B.GREEN
    assert resolve_bucket("terracotta") == B.BROWN


def test_resolve_unmapped_or_empty_is_none():
    assert resolve_bucket("plaid") is None
    assert resolve_bucket("   ") is None


# --- search -----------------------------------------------------------------
def test_search_by_bucket():
    pairs = [_pair("m1", [B.GREEN], name="Sage Mist"), _pair("m2", [B.BLUE], name="Navy")]
    resp = search("green", pairs)
    assert resp.bucket == B.GREEN and resp.count == 1
    assert resp.results[0].material_id == "m1"
    assert resp.results[0].swatch_name == "Sage Mist"  # joined display field


def test_search_via_synonym():
    pairs = [_pair("m1", [B.GREEN], name="Sage Mist"), _pair("m3", [B.GREEN], name="Forest")]
    resp = search("sage", pairs)
    assert resp.bucket == B.GREEN and resp.count == 2


def test_search_unmapped_term_with_no_text_match_returns_empty():
    resp = search("plaid", [_pair("m1", [B.GREEN])])
    assert resp.bucket is None and resp.count == 0 and resp.results == []


# --- string matching on name / company (the §10 expansion) ------------------
def test_search_matches_swatch_name_even_when_bucket_differs():
    # "Navy/Ivory" classified white, not blue — "navy" must still surface it.
    pairs = [_pair("m1", [B.WHITE], name="Navy/Ivory")]
    resp = search("navy", pairs)
    assert resp.bucket == B.BLUE  # the term still resolves
    assert [r.material_id for r in resp.results] == ["m1"]  # found via the name


def test_search_matches_company_name():
    pairs = [_pair("m1", [B.GREEN], name="Sage", company="Daltile")]
    assert search("daltile", pairs).count == 1


def test_search_unmapped_term_still_matches_text():
    # "carrara" maps to no bucket but is a swatch name -> string match surfaces it.
    pairs = [_pair("m1", [B.WHITE], name="Carrara")]
    resp = search("carrara", pairs)
    assert resp.bucket is None and [r.material_id for r in resp.results] == ["m1"]


# --- ranking: best color match, then string match ---------------------------
def test_color_match_outranks_name_only_match():
    # 100%-confidence orange bucket beats a swatch merely named "orange".
    pairs = [
        _pair("named", [B.RED], name="Orange"),          # string-only
        _pair("bucketed", [B.ORANGE], name="Sunset", confidence=1.0),  # color-only
    ]
    resp = search("orange", pairs)
    assert [r.material_id for r in resp.results] == ["bucketed", "named"]


def test_both_color_and_string_ranks_on_top():
    pairs = [
        _pair("color_only", [B.ORANGE], name="Sunset", confidence=1.0),
        _pair("string_only", [B.RED], name="Orange Peel"),
        _pair("both", [B.ORANGE], name="Orange Glow", confidence=0.7),
    ]
    resp = search("orange", pairs)
    # combo first (even at lower confidence), then the pure color match, then string-only.
    assert [r.material_id for r in resp.results] == ["both", "color_only", "string_only"]


def test_color_matches_ordered_by_confidence():
    pairs = [
        _pair("low", [B.GREEN], name="A", confidence=0.6),
        _pair("high", [B.GREEN], name="B", confidence=0.95),
    ]
    resp = search("green", pairs)
    assert [r.material_id for r in resp.results] == ["high", "low"]


def test_search_skips_needs_review_records_on_color_match():
    # A pending-review record must NOT surface as a color (bucket) match.
    pairs = [_pair("m1", [B.GREEN]), _pair("m2", [B.GREEN], needs_review=True)]
    resp = search("green", pairs)
    assert [r.material_id for r in resp.results] == ["m1"]


def test_needs_review_record_still_matches_by_name():
    # ...but it IS findable by the name/company text the user typed (badged in UI).
    pairs = [_pair("m1", [B.WHITE], name="Navy/Ivory", needs_review=True)]
    resp = search("navy", pairs)
    assert [r.material_id for r in resp.results] == ["m1"]
    assert resp.results[0].needs_review is True  # UI can badge it ⚠ review


def test_published_color_match_outranks_review_name_match():
    pairs = [
        _pair("review", [B.WHITE], name="Navy/Ivory", needs_review=True),  # string-only
        _pair("published", [B.BLUE], name="Ocean"),                         # color match
    ]
    resp = search("navy", pairs)
    assert [r.material_id for r in resp.results] == ["published", "review"]


def test_search_multi_bucket_record_matches_each():
    pairs = [_pair("m1", [B.ORANGE, B.BROWN], name="Terracotta Sun")]
    assert search("orange", pairs).count == 1
    assert search("brown", pairs).count == 1
    assert search("blue", pairs).count == 0


# --- the loader (round-trips run_batch's output format) ---------------------
def test_load_classified_joins_and_skips_review(tmp_path):
    fixtures = tmp_path / "records.json"
    fixtures.write_text(
        '[{"material_id": "m1", "swatch_name": "Sage Mist", "company": "GreenBuild"},'
        ' {"material_id": "m2", "swatch_name": "Navy"}]'
    )
    # write via the real sink so the format matches run_batch exactly
    with FileColorSink(tmp_path) as sink:
        sink.write(_pair("m1", [B.GREEN])[1])
        sink.write(_pair("m2", [B.BLUE], needs_review=True)[1])  # -> review_queue, not loaded

    pairs = load_classified(output_dir=tmp_path, fixtures=fixtures)
    assert [m.material_id for m, _ in pairs] == ["m1"]          # review record excluded
    material, record = pairs[0]
    assert material.swatch_name == "Sage Mist"                  # joined from fixtures
    assert record.color_groups == [B.GREEN]


def test_load_classified_missing_output_returns_empty(tmp_path):
    fixtures = tmp_path / "records.json"
    fixtures.write_text('[{"material_id": "m1"}]')
    assert load_classified(output_dir=tmp_path, fixtures=fixtures) == []


def test_default_synonyms_only_map_to_valid_buckets():
    assert all(isinstance(v, ColorBucket) for v in DEFAULT_SYNONYMS.values())
