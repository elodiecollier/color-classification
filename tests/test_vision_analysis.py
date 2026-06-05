"""Tests for core/vision_analysis — the advisory third opinion (§3 amendment).

Fake vision client (no network); same defensive-parsing contract as the name
signal: out-of-taxonomy / malformed output degrades to no-signal, never raises.
"""

from __future__ import annotations

from core.models import ColorBucket
from core.vision_analysis import analyze_image_vision


class FakeVisionLLM:
    """Returns a canned response; records what it was shown."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def complete_json_vision(self, *, system: str, user: str, image_bytes: bytes, mime_type: str) -> str:
        self.calls.append({"system": system, "image_bytes": image_bytes, "mime": mime_type})
        return self.payload


def test_valid_response_parses():
    fake = FakeVisionLLM('{"buckets": ["black", "white"], "confidence": 0.9}')
    r = analyze_image_vision(b"png-bytes", fake)
    assert r.buckets == [ColorBucket.BLACK, ColorBucket.WHITE]
    assert r.confidence == 0.9
    assert fake.calls[0]["image_bytes"] == b"png-bytes"


def test_out_of_taxonomy_dropped():
    fake = FakeVisionLLM('{"buckets": ["taupe", "grey"], "confidence": 0.7}')
    assert analyze_image_vision(b"x", fake).buckets == [ColorBucket.GREY]


def test_malformed_json_is_no_signal():
    r = analyze_image_vision(b"x", FakeVisionLLM("i am not json"))
    assert r.buckets == [] and r.confidence == 0.0


def test_transport_error_is_no_signal():
    class Exploding:
        def complete_json_vision(self, **_):
            raise RuntimeError("boom")

    r = analyze_image_vision(b"x", Exploding())
    assert r.buckets == [] and r.confidence == 0.0
