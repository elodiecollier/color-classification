"""The single config constant holding every tunable threshold (CLAUDE.md §5).

Will define one frozen config object (a pydantic model or frozen dataclass)
with a module-level default instance, covering:

BUCKETING (core/buckets.py)
  - Hue band boundaries for the six chromatic buckets:
    red / orange / yellow / green / blue / purple.
    Boundary choices per §5: cyan folds into blue/green, pink folds into red.
  - Achromatic cutoffs — checked FIRST, before any hue logic:
      * saturation below which a color is achromatic
      * lightness near 0 -> black, near 100 -> white, otherwise grey
  - Brown rule — checked BEFORE falling into orange/red:
      * orange/red hue range + low-lightness ceiling + saturation window
  - Optional light/dark lightness sub-tier: boundary values + an enable flag
    (config-gated, off by default).

IMAGE PIPELINE (core/image_pipeline.py + adapters/clustering)
  - Downscale target (max edge ~200px).
  - Cluster k-sweep range (1..6) for the K-means strategy.
  - Relevance filter: minimum coverage % for a cluster to survive.
  - ΔE merge distance: clusters closer than this merge; anything farther
    apart must NOT merge (checkerboard -> black + white, never grey).

CONFIDENCE / RECONCILIATION (core/reconcile.py, core/name_analysis.py)
  - Name-analysis confidence floor below which the name pre-check is
    treated as "not intuitive" and we fall through to the image.
  - Agreement/conflict confidence values assigned by reconciliation.
  - needs_review cutoff.

Tuning happens by editing this file only — see CLAUDE.md §13 step 8.
Known watch-item to revisit here: a possible neutral/beige bucket (§5).
"""
