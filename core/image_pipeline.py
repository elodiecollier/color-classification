"""Deterministic image -> color extraction (CLAUDE.md §7).

AUTHORITATIVE signal whenever a swatch image exists — names lie ("Fall River
Glaze"); pixels don't. Explicitly NOT an LLM call: multi-tone / gradient /
checkerboard swatches need real clustering (a black/white checkerboard must
classify as black + white, NOT gray).

Orchestrates, in order:
  1. Downscale (max edge from config, ~200px) — bounds clustering cost.
  2. Convert pixels to CIELAB (perceptually uniform; distances mean
     something there, unlike RGB/HSL).
  3. Cluster pixels via the injected `ports.clustering` strategy
     (K-means k-sweep + silhouette, or HDBSCAN — swappable, this module
     never names a concrete algorithm).
  4. Per cluster: centroid color + coverage %.
  5. RELEVANCE FILTER:
       - drop clusters below the config coverage threshold
       - merge clusters within the config ΔE distance
       - never merge perceptually distant clusters (the checkerboard rule)
  6. Surviving centroids: LAB -> HSL -> bucket(s) via core/buckets.py.

Returns an ImageAnalysisResult (core/models.py) carrying BOTH the buckets
and the raw lab_centroids + coverage — centroids are persisted even now as
a durable asset (§4, §8).

I/O note: receives image BYTES (fetched by the caller through
ports/image_store.py); this module itself does no I/O. The pixel-math
helpers it needs (LAB conversion, ΔE) come in with the clustering adapter's
deps, injected alongside the strategy, keeping core import-clean.
"""
