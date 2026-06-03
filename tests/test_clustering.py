"""Executable spec for the k-means workstream. Make these green, in order:

    uv run pytest tests/test_clustering.py -x

Part 1 (KMeansSweep) uses synthetic LAB pixel arrays — no images needed.
Part 2 (preprocess) generates tiny images in memory — no fixture files needed.
"""

import io

import numpy as np
import pytest

from adapters.clustering.kmeans_sweep import KMeansSweep


def noisy_blob(lab, n, spread, rng):
    """n pixels normally scattered around one LAB color."""
    return rng.normal(loc=lab, scale=spread, size=(n, 3))


@pytest.fixture
def rng():
    return np.random.default_rng(42)


# ---------------------------------------------------------------------------
# Part 1 — KMeansSweep
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list():
    assert KMeansSweep().cluster(np.empty((0, 3))) == []


def test_solid_swatch_is_one_cluster(rng):
    """The common case: one color -> one cluster via the STEP 1 shortcut."""
    pixels = noisy_blob([60.0, 5.0, 5.0], n=1000, spread=0.3, rng=rng)
    clusters = KMeansSweep().cluster(pixels)
    assert len(clusters) == 1
    assert clusters[0].coverage == pytest.approx(1.0)
    assert clusters[0].lab == pytest.approx((60.0, 5.0, 5.0), abs=1.0)


def test_checkerboard_is_black_plus_white_never_grey(rng):
    """THE acid test (CLAUDE.md §3): 50/50 black + white pixels must yield
    two clusters at the extremes — a single mid-grey centroid is the failure
    mode this whole design exists to prevent."""
    black = noisy_blob([2.0, 0.0, 0.0], n=500, spread=1.0, rng=rng)
    white = noisy_blob([98.0, 0.0, 0.0], n=500, spread=1.0, rng=rng)
    pixels = np.vstack([black, white])

    clusters = KMeansSweep().cluster(pixels)

    assert len(clusters) == 2
    lightnesses = sorted(c.lab[0] for c in clusters)
    assert lightnesses[0] == pytest.approx(2.0, abs=3.0)   # black survived
    assert lightnesses[1] == pytest.approx(98.0, abs=3.0)  # white survived
    for c in clusters:
        assert not (30 < c.lab[0] < 70), f"got a grey centroid: {c.lab}"
        assert c.coverage == pytest.approx(0.5, abs=0.05)


def test_three_tone_coverage_proportions(rng):
    """Multi-tone swatch: cluster count AND coverage fractions must be right
    — coverage drives the relevance filter downstream."""
    pixels = np.vstack(
        [
            noisy_blob([50.0, 60.0, 40.0], n=600, spread=1.0, rng=rng),   # red-ish, 60%
            noisy_blob([55.0, -50.0, 45.0], n=300, spread=1.0, rng=rng),  # green-ish, 30%
            noisy_blob([30.0, 20.0, -60.0], n=100, spread=1.0, rng=rng),  # blue-ish, 10%
        ]
    )
    clusters = KMeansSweep().cluster(pixels)
    assert len(clusters) == 3
    assert [round(c.coverage, 1) for c in clusters] == [0.6, 0.3, 0.1]


def test_sorted_by_coverage_descending(rng):
    pixels = np.vstack(
        [
            noisy_blob([20.0, 0.0, 0.0], n=200, spread=1.0, rng=rng),
            noisy_blob([80.0, 0.0, 0.0], n=800, spread=1.0, rng=rng),
        ]
    )
    clusters = KMeansSweep().cluster(pixels)
    coverages = [c.coverage for c in clusters]
    assert coverages == sorted(coverages, reverse=True)


def test_deterministic_across_runs(rng):
    """Same image -> identical answer, always (fixed seeds everywhere)."""
    pixels = np.vstack(
        [
            noisy_blob([30.0, 10.0, 10.0], n=400, spread=1.5, rng=rng),
            noisy_blob([70.0, -20.0, 30.0], n=600, spread=1.5, rng=rng),
        ]
    )
    a = KMeansSweep().cluster(pixels.copy())
    b = KMeansSweep().cluster(pixels.copy())
    assert a == b


def test_tiny_input_does_not_crash(rng):
    """Degenerate input (fewer pixels than k_max) must still return sanely."""
    pixels = noisy_blob([50.0, 0.0, 0.0], n=3, spread=0.1, rng=rng)
    clusters = KMeansSweep().cluster(pixels)
    assert len(clusters) >= 1
    assert sum(c.coverage for c in clusters) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Part 2 — preprocess (implement after Part 1 is green)
# ---------------------------------------------------------------------------


def _png_bytes(pixels_rgb: np.ndarray) -> bytes:
    """Encode an (H, W, 3) uint8 array as PNG bytes, in memory."""
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(pixels_rgb, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_preprocess_decodes_and_flattens():
    from adapters.clustering.preprocess import load_lab_pixels

    img = np.full((10, 10, 3), 255, dtype=np.uint8)  # 10x10 pure white
    lab = load_lab_pixels(_png_bytes(img))
    assert lab is not None
    assert lab.shape == (100, 3)
    # White is L=100, a=0, b=0 — if L comes back ~0.0 or ~255-scaled, the
    # /255 normalization before rgb2lab was missed (the classic bug).
    assert lab[0][0] == pytest.approx(100.0, abs=1.0)


def test_preprocess_downscales_large_images():
    from adapters.clustering.preprocess import load_lab_pixels

    img = np.zeros((1000, 500, 3), dtype=np.uint8)
    lab = load_lab_pixels(_png_bytes(img), max_edge=200)
    assert lab is not None
    assert len(lab) <= 200 * 100  # aspect ratio kept: 1000x500 -> 200x100


def test_preprocess_checkerboard_keeps_both_extremes():
    """End-to-end sanity: checkerboard PNG -> LAB pixels at BOTH extremes."""
    from adapters.clustering.preprocess import load_lab_pixels

    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[::2, 1::2] = 255
    img[1::2, ::2] = 255
    lab = load_lab_pixels(_png_bytes(img))
    assert lab is not None
    lightness = lab[:, 0]
    assert lightness.min() == pytest.approx(0.0, abs=1.0)
    assert lightness.max() == pytest.approx(100.0, abs=1.0)


def test_preprocess_garbage_bytes_returns_none():
    """Undecodable image is a NORMAL §6 branch, not an exception."""
    from adapters.clustering.preprocess import load_lab_pixels

    assert load_lab_pixels(b"not an image at all") is None
