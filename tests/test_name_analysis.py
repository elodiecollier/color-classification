"""Tests for core/name_analysis — name -> buckets + confidence (§6 step 1, §9).

Uses a fake LLM client (no API key, no network): we control the raw JSON and
assert the parse / validate / defensive behaviour.
"""

from __future__ import annotations

from core.models import ColorBucket
from core.name_analysis import analyze_name


class FakeLLM:
    """Returns a canned response; records the prompts it was given."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.payload


def test_descriptive_name_resolves_high_confidence():
    r = analyze_name("Sage", FakeLLM('{"buckets": ["green"], "confidence": 0.92}'))
    assert r.buckets == [ColorBucket.GREEN]
    assert r.confidence == 0.92


def test_multi_bucket_name():
    r = analyze_name("Terracotta", FakeLLM('{"buckets": ["orange", "brown"], "confidence": 0.7}'))
    assert set(r.buckets) == {ColorBucket.ORANGE, ColorBucket.BROWN}


def test_non_intuitive_name_low_confidence_no_buckets():
    r = analyze_name("Fall River Glaze", FakeLLM('{"buckets": [], "confidence": 0.05}'))
    assert r.buckets == []
    assert r.confidence == 0.05


def test_out_of_taxonomy_values_dropped_and_deduped():
    r = analyze_name("X", FakeLLM('{"buckets": ["green", "mauve", "GREEN"], "confidence": 0.8}'))
    assert r.buckets == [ColorBucket.GREEN]  # 'mauve' dropped; 'GREEN' normalised + deduped


def test_malformed_json_is_no_signal():
    r = analyze_name("X", FakeLLM("definitely not json"))
    assert r.buckets == [] and r.confidence == 0.0


def test_confidence_clamped_to_unit_interval():
    assert analyze_name("X", FakeLLM('{"buckets": ["red"], "confidence": 1.5}')).confidence == 1.0
    assert analyze_name("X", FakeLLM('{"buckets": ["red"], "confidence": -3}')).confidence == 0.0


def test_empty_name_short_circuits_without_calling_llm():
    fake = FakeLLM('{"buckets": ["green"], "confidence": 1.0}')
    r = analyze_name("   ", fake)
    assert r.buckets == [] and r.confidence == 0.0
    assert fake.calls == []  # no LLM call for an empty name


def test_company_is_passed_in_the_prompt():
    fake = FakeLLM('{"buckets": ["blue"], "confidence": 0.6}')
    analyze_name("Harbor", fake, company="SteelWorks")
    assert "SteelWorks" in fake.calls[0][1]
