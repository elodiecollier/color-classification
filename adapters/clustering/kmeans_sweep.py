"""ClusteringStrategy: K-means with k-sweep + silhouette selection (CLAUDE.md §7).

YOUR IMPLEMENTATION TASK — fill in the STEP blocks in cluster() below.
The executable spec is tests/test_clustering.py; you're done when it's green:

    uv run pytest tests/test_clustering.py -x

Config note: thresholds are constructor params (with defaults) for now, so
this module is testable in isolation. Once config/thresholds.py lands
(partner workstream), cli/run_batch.py constructs this FROM config — do not
import config here.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from ports.clustering import ClusterResult


class KMeansSweep:
    """Implements ports.clustering.ClusteringStrategy."""

    def __init__(
        self,
        k_max: int = 6,
        solid_delta_e: float = 2.0,
        silhouette_sample: int = 2000,
        seed: int = 0,
    ) -> None:
        # k_max:             upper end of the sweep (k = 2..k_max).
        # solid_delta_e:     "is this a solid swatch?" spread cutoff — ΔE76 is
        #                    just Euclidean distance in LAB; ~2.3 is the
        #                    just-noticeable difference, so 2.0 is conservative.
        # silhouette_sample: silhouette is O(N²); score on at most this many
        #                    sampled pixels.
        # seed:              fix ALL randomness (k-means init + silhouette
        #                    sampling) — same image must always give the same
        #                    answer.
        self.k_max = k_max
        self.solid_delta_e = solid_delta_e
        self.silhouette_sample = silhouette_sample
        self.seed = seed

    def cluster(self, lab_pixels: np.ndarray) -> list[ClusterResult]:
        """Group LAB pixels into dominant colors (see ports/clustering.py)."""
        # STEP 0 — guard rails. NOTE: `if not lab_pixels` crashes on numpy
        # arrays (truthiness is ambiguous for >1 element); check length.
        n = len(lab_pixels)
        if n == 0:
            return []

        # STEP 1 — solid-swatch shortcut (the common case; k=1 also can't be
        # silhouette-scored). If every pixel sits within ~solid_delta_e of the
        # mean color, this is one color — done.
        mean_color = lab_pixels.mean(axis=0)
        spread = np.linalg.norm(lab_pixels - mean_color, axis=1).mean()
        solid = [ClusterResult(lab=_as_tuple(mean_color), coverage=1.0)]
        if spread < self.solid_delta_e:
            return solid

        # STEP 2 — the sweep: fit k-means for each k, score by silhouette.
        best: tuple[float, KMeans, np.ndarray] | None = None
        for k in range(2, self.k_max + 1):
            if k > n - 1:  # silhouette needs 2 <= k <= N-1
                break
            km = KMeans(n_clusters=k, n_init="auto", random_state=self.seed)
            labels = km.fit_predict(lab_pixels)
            if len(np.unique(labels)) < 2:  # degenerate fit; unscoreable
                continue
            score = silhouette_score(
                lab_pixels,
                labels,
                sample_size=min(self.silhouette_sample, n),
                random_state=self.seed,
            )
            # STEP 3 — keep the best-scoring fit.
            if best is None or score > best[0]:
                best = (score, km, labels)

        if best is None:  # nothing scoreable (e.g. 2 near-identical pixels)
            return solid

        # STEP 4 — shape the output: centroid + coverage per cluster,
        # largest coverage first.
        _, km, labels = best
        results = [
            ClusterResult(
                lab=_as_tuple(km.cluster_centers_[i]),
                coverage=float((labels == i).sum()) / n,
            )
            for i in range(km.n_clusters)
        ]
        return sorted(results, key=lambda c: c.coverage, reverse=True)


def _as_tuple(centroid: np.ndarray) -> tuple[float, float, float]:
    """numpy (3,) array -> plain (L, a, b) float tuple for ClusterResult."""
    l_val, a_val, b_val = (float(v) for v in centroid)
    return (l_val, a_val, b_val)
