"""Deterministic image -> color extraction (CLAUDE.md §6 step 2, §7).

Orchestration only, and import-clean: the heavy steps (image decode + LAB via
`load_pixels`, pixel clustering via the `strategy`) are INJECTED, so `core/`
pulls no numpy/sklearn/PIL and this is unit-testable with a fake strategy. The
relevance filter here is pure-Python ΔE76 (Euclidean distance in CIELAB) over
the FEW centroids a strategy returns — no numpy needed.

Pipeline:
    bytes -> load_pixels(max_edge) -> strategy.cluster -> relevance filter
          -> buckets_for_centroids -> ImageAnalysisResult

Relevance filter (§7): MERGE centroids within `merge_delta_e` (coverage-weighted),
THEN DROP those below `min_coverage`; perceptually distant clusters never merge,
so a black/white checkerboard stays black + white (never grey). Returns None when
the image can't be decoded or yields no usable color — the §6 signal to fall
through to name-only / review.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from config.thresholds import DEFAULT, ClusteringThresholds, Thresholds
from core.buckets import buckets_for_centroids, lab_to_hsl
from core.models import ClusterResult, ImageAnalysisResult, LabColor

if TYPE_CHECKING:  # imports kept out of the runtime path so core/ stays numpy-free
    from collections.abc import Callable

    import numpy as np

    from ports.clustering import ClusteringStrategy

    PixelLoader = Callable[[bytes, int], np.ndarray | None]


def analyze_swatch(
    image_bytes: bytes,
    *,
    load_pixels: PixelLoader,
    strategy: ClusteringStrategy,
    config: Thresholds = DEFAULT,
) -> ImageAnalysisResult | None:
    """Extract the dominant color bucket(s) from a swatch image.

    `load_pixels` is `adapters.clustering.preprocess.load_lab_pixels`; `strategy`
    is a `ports.clustering.ClusteringStrategy` (e.g. `KMeansSweep()`). Returns
    None when the image is undecodable or yields nothing usable.
    """
    cfg = config.clustering

    pixels = load_pixels(image_bytes, cfg.max_edge)
    if pixels is None or len(pixels) == 0:
        return None

    clusters = strategy.cluster(pixels)
    survivors = _relevance_filter(clusters, cfg)
    if not survivors:
        return None

    dominant = survivors[0]
    return ImageAnalysisResult(
        buckets=buckets_for_centroids(survivors, config.bucketing),
        centroids=survivors,
        canonical_hsl=lab_to_hsl(_lab_color(dominant.lab)),
    )


def _relevance_filter(
    clusters: list[ClusterResult], cfg: ClusteringThresholds
) -> list[ClusterResult]:
    """Merge near-duplicate centroids, then drop the insignificant ones."""
    merged = _merge_near(clusters, cfg.merge_delta_e)
    kept = [c for c in merged if c.coverage >= cfg.min_coverage]
    # If everything was sub-threshold (e.g. many tiny clusters), keep the
    # single largest rather than returning nothing.
    if not kept and merged:
        kept = [max(merged, key=lambda c: c.coverage)]
    return sorted(kept, key=lambda c: c.coverage, reverse=True)


def _merge_near(clusters: list[ClusterResult], merge_delta_e: float) -> list[ClusterResult]:
    """Greedily merge the closest pair within `merge_delta_e` until none remain.

    Operates on the handful of centroids a strategy returns, so the O(n²) sweep
    is trivial. Distant clusters are never merged (the checkerboard guarantee).
    """
    items = list(clusters)
    while len(items) > 1:
        closest: tuple[float, int, int] | None = None
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                dist = _delta_e(items[i].lab, items[j].lab)
                if dist <= merge_delta_e and (closest is None or dist < closest[0]):
                    closest = (dist, i, j)
        if closest is None:
            break
        _, i, j = closest
        items[i] = _merge_two(items[i], items[j])
        del items[j]
    return items


def _merge_two(a: ClusterResult, b: ClusterResult) -> ClusterResult:
    """Coverage-weighted merge of two centroids."""
    total = a.coverage + b.coverage
    if total <= 0:
        return ClusterResult(lab=a.lab, coverage=0.0)
    lab = tuple((a.lab[k] * a.coverage + b.lab[k] * b.coverage) / total for k in range(3))
    return ClusterResult(lab=lab, coverage=total)  # type: ignore[arg-type]


def _delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """ΔE76 — Euclidean distance in CIELAB (matches the clustering adapter)."""
    return math.dist(a, b)


def _lab_color(lab: tuple[float, float, float]) -> LabColor:
    """(L, a, b) tuple -> LabColor, with L clamped to the valid [0, 100] range."""
    L, a, b = lab
    return LabColor(L=min(max(L, 0.0), 100.0), a=a, b=b)
