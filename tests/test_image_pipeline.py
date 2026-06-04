"""Tests for core/image_pipeline.py (§6 step 2, §7).

Most tests use a FAKE clustering strategy (canned ClusterResults) — fast,
deterministic, no images/sklearn — to exercise the relevance filter. One
end-to-end test runs a real PNG through the real preprocess + KMeansSweep.
"""

from __future__ import annotations

import io

from core.image_pipeline import analyze_swatch
from core.models import ClusterResult, ColorBucket

B = ColorBucket
_PIXELS = [[0.0, 0.0, 0.0]]  # non-empty sentinel; the fake strategy ignores it


class FakeStrategy:
    """Returns canned clusters, ignoring the pixels."""

    def __init__(self, clusters: list[ClusterResult]) -> None:
        self._clusters = clusters

    def cluster(self, pixels) -> list[ClusterResult]:
        return list(self._clusters)


def _loader(returns):
    """A fake load_pixels that yields `returns` regardless of input."""
    def _load(image_bytes: bytes, max_edge: int):
        return returns
    return _load


def _run(clusters, *, pixels=_PIXELS):
    return analyze_swatch(b"", load_pixels=_loader(pixels), strategy=FakeStrategy(clusters))


# --- the relevance filter ---------------------------------------------------
def test_solid_swatch_one_bucket():
    res = _run([ClusterResult(lab=(50.0, -40.0, 30.0), coverage=1.0)])
    assert res is not None
    assert res.buckets == [B.GREEN]
    assert len(res.centroids) == 1
    assert res.canonical_hsl is not None


def test_near_duplicate_clusters_merge():
    # two greens within ~ΔE 1.7 -> merge into one, coverage summed
    res = _run([
        ClusterResult(lab=(50.0, -40.0, 30.0), coverage=0.3),
        ClusterResult(lab=(51.0, -39.0, 31.0), coverage=0.3),
    ])
    assert res.buckets == [B.GREEN]
    assert len(res.centroids) == 1
    assert res.centroids[0].coverage == 0.6


def test_distant_clusters_never_merge_checkerboard():
    # black + white are ΔE ~96 apart -> stay two clusters, never one grey
    res = _run([
        ClusterResult(lab=(2.0, 0.0, 0.0), coverage=0.5),
        ClusterResult(lab=(98.0, 0.0, 0.0), coverage=0.5),
    ])
    assert set(res.buckets) == {B.BLACK, B.WHITE}
    assert len(res.centroids) == 2


def test_subthreshold_cluster_is_dropped():
    # a 4% speck (< min_coverage 0.05) is dropped; only the green remains
    res = _run([
        ClusterResult(lab=(50.0, -40.0, 30.0), coverage=0.96),
        ClusterResult(lab=(50.0, 70.0, 50.0), coverage=0.04),
    ])
    assert res.buckets == [B.GREEN]
    assert len(res.centroids) == 1


def test_all_subthreshold_keeps_dominant():
    # everything below threshold -> keep the single largest, not nothing
    res = _run([
        ClusterResult(lab=(50.0, -40.0, 30.0), coverage=0.03),
        ClusterResult(lab=(50.0, 70.0, 50.0), coverage=0.02),
    ])
    assert res is not None
    assert len(res.centroids) == 1
    assert res.centroids[0].coverage == 0.03


def test_centroids_kept_as_durable_asset():
    res = _run([ClusterResult(lab=(32.30, 79.19, -107.86), coverage=1.0)])  # blue
    assert res.buckets == [B.BLUE]
    assert res.centroids[0].lab == (32.30, 79.19, -107.86)


# --- None paths (-> fall through to name-only / review, §6) -----------------
def test_undecodable_image_returns_none():
    assert _run([ClusterResult(lab=(50.0, 0.0, 0.0), coverage=1.0)], pixels=None) is None


def test_empty_pixels_returns_none():
    assert _run([ClusterResult(lab=(50.0, 0.0, 0.0), coverage=1.0)], pixels=[]) is None


def test_no_clusters_returns_none():
    assert _run([]) is None


# --- one real end-to-end through preprocess + KMeansSweep -------------------
def test_end_to_end_solid_green_png():
    import numpy as np
    from PIL import Image

    from adapters.clustering.kmeans_sweep import KMeansSweep
    from adapters.clustering.preprocess import load_lab_pixels

    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[:, :] = (110, 150, 90)  # a sage-ish green
    buf = io.BytesIO()
    Image.fromarray(img, "RGB").save(buf, "PNG")

    res = analyze_swatch(buf.getvalue(), load_pixels=load_lab_pixels, strategy=KMeansSweep())
    assert res is not None
    assert res.buckets == [B.GREEN]
    assert res.canonical_hsl is not None
