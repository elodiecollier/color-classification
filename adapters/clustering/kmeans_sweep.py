"""ClusteringStrategy: K-means with k-sweep + silhouette selection (§7).

Implements ports/clustering.py. Runs K-means over LAB pixels for each k in
the config sweep range (1..6), picks the k with the best silhouette score,
and returns per-cluster LAB centroids + coverage %.

Notes for implementation:
  - k=1 needs special-casing (silhouette is undefined for a single
    cluster) — a solid-color swatch is the common case, not an edge case.
  - Fixed random seed: classification must be reproducible run-to-run.
  - Operates on the already-downscaled pixel set (image_pipeline downsizes
    first), so cost is bounded.
"""
