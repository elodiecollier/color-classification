"""Pluggable clustering strategies behind ports/clustering.py (CLAUDE.md §7).

Located in adapters/ (not core/) purely for dependency hygiene: these pull
in numpy / scikit-learn / scikit-image / hdbscan, which core/ must not
depend on. The algorithms themselves are deterministic math (fixed seeds —
same image must always yield the same clusters).

  kmeans_sweep.py  K-means, k swept 1..config-max, silhouette selection.
                  The default strategy.
  hdbscan.py      density-based alternative; finds k itself. Kept behind
                  the same interface so the two can be A/B'd on real
                  swatches without touching core/image_pipeline.py.

Shared pixel-math helpers (RGB->LAB conversion, ΔE distance) that the
image pipeline needs are exposed from here too — same dep-hygiene reason.
"""
