"""Port: the swappable pixel-clustering algorithm (CLAUDE.md §7, §11).

core/image_pipeline.py orchestrates the steps but never names a concrete
algorithm — it calls this interface. That keeps the heavy CV deps
(numpy / scikit-learn / hdbscan) OUT of core/ and lets us A/B the two
candidate strategies against real swatches without touching the pipeline.

Will define:
  - ClusterResult: per-cluster LAB centroid + coverage % (pre-filter; the
    relevance filter in image_pipeline.py runs on top of this).
  - ClusteringStrategy (interface):
      cluster(lab_pixels) -> list[ClusterResult]

Implementations (adapters/clustering/):
  - KMeansSweep: K-means with k swept over the config range (1..6),
    selected by silhouette score.
  - HDBSCANStrategy: density-based alternative; no k to pick.

The acid test for any implementation + the downstream filter: a black/white
checkerboard must come out as TWO clusters (black + white), never one grey.
"""
