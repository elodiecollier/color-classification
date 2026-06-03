"""Tests for core/image_pipeline.py + the clustering adapters (§7).

Uses tiny generated images (solid, two-tone, gradient) — no fixtures from
disk needed for the unit level. Must cover:
  - solid swatch -> exactly one centroid, ~100% coverage
  - THE CHECKERBOARD TEST (the §3 acid test): black/white checkerboard ->
    two clusters, black + white, NEVER a single grey
  - relevance filter: a sub-threshold speck cluster is dropped
  - ΔE merge: two near-identical clusters merge; distant ones never do
  - lab_centroids + coverage are present on the result (the durable asset)
  - determinism: same image -> identical result across runs (fixed seeds)
  - strategy swap: kmeans_sweep and hdbscan run behind the same port
"""
