"""Port: the swappable pixel-clustering algorithm (CLAUDE.md §7, §11).

core/image_pipeline.py orchestrates the steps but never names a concrete
algorithm — it calls this interface. That keeps the heavy CV deps
(numpy / scikit-learn) OUT of core/ and lets us A/B strategies against
real swatches without touching the pipeline.

Dependency note: numpy IS allowed here (unlike in core/) — a pixel array
is the only sane interchange format between the pipeline and a strategy.

The acid test for any implementation: a black/white checkerboard must come
out as TWO clusters (black + white), never one grey.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

# Single source of truth for the type lives in core/models.py (numpy-free) so
# core/buckets.py can consume it without importing numpy. Re-exported here for
# the adapters' convenience (`from ports.clustering import ClusterResult`).
from core.models import ClusterResult

__all__ = ["ClusterResult", "ClusteringStrategy"]


class ClusteringStrategy(Protocol):
    """Interface implemented by adapters/clustering/* (KMeansSweep, HDBSCAN)."""

    def cluster(self, lab_pixels: np.ndarray) -> list[ClusterResult]:
        """Group pixels into dominant colors.

        Args:
            lab_pixels: float array of shape (N, 3) — one CIELAB color per
                pixel, already downscaled by the caller.

        Returns:
            Clusters sorted by coverage, largest first. Empty input -> [].
            Must be deterministic: same input always yields the same output.
        """
        ...
