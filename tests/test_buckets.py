"""Tests for core/buckets.py against synthetic colors (§13 step 3).

The spine module — these tests gate everything downstream.
"""

from __future__ import annotations

import pytest

from core.buckets import bucket_for_hsl, buckets_for_centroids, lab_to_hsl
from core.models import ClusterResult, ColorBucket, HSL, LabColor

B = ColorBucket


# --- one obvious in-band color per chromatic bucket -------------------------
@pytest.mark.parametrize(
    "hue, expected",
    [
        (0, B.RED),
        (30, B.ORANGE),
        (60, B.YELLOW),
        (120, B.GREEN),
        (210, B.BLUE),
        (280, B.PURPLE),
    ],
)
def test_chromatic_buckets(hue, expected):
    # mid-lightness, fully saturated -> lands on the hue band
    assert bucket_for_hsl(HSL(h=hue, s=1.0, l=0.5)) == expected


# --- achromatic first -------------------------------------------------------
def test_low_saturation_is_grey_regardless_of_hue():
    for hue in (0, 120, 210, 300):
        assert bucket_for_hsl(HSL(h=hue, s=0.02, l=0.5)) == B.GREY


def test_extreme_lightness_overrides_hue():
    # a saturated green that's nearly black/white is black/white, not green
    assert bucket_for_hsl(HSL(h=120, s=0.9, l=0.03)) == B.BLACK
    assert bucket_for_hsl(HSL(h=120, s=0.9, l=0.97)) == B.WHITE


# --- brown rule (and that it doesn't overreach) -----------------------------
def test_dark_orange_is_brown():
    assert bucket_for_hsl(HSL(h=30, s=0.8, l=0.30)) == B.BROWN


def test_bright_orange_stays_orange():
    # same hue, high lightness -> the brown rule must NOT fire
    assert bucket_for_hsl(HSL(h=30, s=1.0, l=0.55)) == B.ORANGE


# --- boundary folds (cyan -> blue/green, pink -> red) -----------------------
def test_cyan_folds_into_blue():
    assert bucket_for_hsl(HSL(h=185, s=0.9, l=0.5)) == B.BLUE


def test_pink_rose_folds_into_red():
    assert bucket_for_hsl(HSL(h=330, s=0.7, l=0.5)) == B.RED


# --- LAB -> HSL conversion + bucketing round-trip ---------------------------
@pytest.mark.parametrize(
    "lab, expected",
    [
        (LabColor(L=53.24, a=80.09, b=67.20), B.RED),    # sRGB pure red
        (LabColor(L=87.74, a=-86.18, b=83.18), B.GREEN), # sRGB pure green
        (LabColor(L=32.30, a=79.19, b=-107.86), B.BLUE), # sRGB pure blue
        (LabColor(L=100.0, a=0.0, b=0.0), B.WHITE),
        (LabColor(L=0.0, a=0.0, b=0.0), B.BLACK),
        (LabColor(L=53.6, a=0.0, b=0.0), B.GREY),        # mid neutral
    ],
)
def test_lab_to_hsl_then_bucket(lab, expected):
    assert bucket_for_hsl(lab_to_hsl(lab)) == expected


# --- buckets_for_centroids: multi-tone, dedup, coverage ordering ------------
def test_checkerboard_is_black_and_white_not_grey():
    centroids = [
        ClusterResult(lab=(0.0, 0.0, 0.0), coverage=0.5),
        ClusterResult(lab=(100.0, 0.0, 0.0), coverage=0.5),
    ]
    assert set(buckets_for_centroids(centroids)) == {B.BLACK, B.WHITE}


def test_centroids_dedup_and_order_by_coverage():
    centroids = [
        ClusterResult(lab=(53.24, 80.09, 67.20), coverage=0.2),   # red
        ClusterResult(lab=(32.30, 79.19, -107.86), coverage=0.5), # blue
        ClusterResult(lab=(53.24, 80.09, 67.20), coverage=0.3),   # red again
    ]
    # red total 0.5 vs blue 0.5 -> tie broken by first appearance (red first)
    assert buckets_for_centroids(centroids) == [B.RED, B.BLUE]
