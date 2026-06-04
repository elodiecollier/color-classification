"""The single config constant holding every tunable threshold (CLAUDE.md §5).

One frozen config object with a module-level default instance, `DEFAULT`.
Tuning happens by editing this file only (CLAUDE.md §13 step 8).

IMPLEMENTED: the BUCKETING section (consumed by core/buckets.py). The clustering
and confidence/reconciliation sections are left as TODO for those workstreams —
add them as new nested models on `Thresholds` so edits stay additive and
conflict-free.

Known watch-item to revisit: a possible neutral/beige bucket (§5).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.models import ColorBucket

_FROZEN = ConfigDict(frozen=True)

# Hue bands for the six chromatic buckets, in degrees. A band (lo, hi) with
# lo < hi matches lo <= h < hi; the wrap-around band (lo > hi, i.e. red) matches
# h >= lo OR h < hi. Bands must tile [0, 360). Boundary choices per §5:
# cyan folds into blue/green, pink/rose folds into red, magenta into purple.
_DEFAULT_HUE_BANDS: tuple[tuple[ColorBucket, float, float], ...] = (
    (ColorBucket.RED, 315.0, 15.0),
    (ColorBucket.ORANGE, 15.0, 45.0),
    (ColorBucket.YELLOW, 45.0, 70.0),
    (ColorBucket.GREEN, 70.0, 165.0),
    (ColorBucket.BLUE, 165.0, 255.0),
    (ColorBucket.PURPLE, 255.0, 315.0),
)


class BucketingThresholds(BaseModel):
    """Thresholds for HSL -> ColorBucket mapping (core/buckets.py).

    Evaluation order is fixed in code (achromatic -> brown -> hue bands); these
    values only move the boundaries.
    """

    model_config = _FROZEN

    # --- Achromatic, checked FIRST (catches checkerboard tiles before hue) ---
    achromatic_max_saturation: float = Field(
        default=0.12, ge=0.0, le=1.0,
        description="At/below this saturation a mid-lightness color is grey",
    )
    black_max_lightness: float = Field(
        default=0.16, ge=0.0, le=1.0,
        description="At/below this lightness -> black, regardless of hue",
    )
    white_min_lightness: float = Field(
        default=0.92, ge=0.0, le=1.0,
        description="At/above this lightness -> white, regardless of hue",
    )

    # --- Brown, checked BEFORE the hue bands (brown is dark/low-sat orange) ---
    brown_hue_min: float = Field(default=15.0, ge=0.0, le=360.0)
    brown_hue_max: float = Field(default=50.0, ge=0.0, le=360.0)
    brown_max_lightness: float = Field(
        default=0.45, ge=0.0, le=1.0,
        description="Orange-hued colors at/below this lightness -> brown, not orange",
    )

    # --- Hue bands for the six chromatic buckets ---
    hue_bands: tuple[tuple[ColorBucket, float, float], ...] = _DEFAULT_HUE_BANDS

    # --- Optional light/dark sub-tier (config-gated, OFF; not yet applied) ---
    enable_light_dark_subtier: bool = Field(
        default=False,
        description="Reserved: emit a light/dark qualifier alongside the bucket",
    )


class ConfidenceThresholds(BaseModel):
    """Confidence cutoffs for the name signal + reconciliation (CLAUDE.md §6, §9)."""

    model_config = _FROZEN

    name_intuitive_floor: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Name-analysis confidence below this counts as 'not intuitive' "
                    "-> fall through to the image (§6 step 1). Applied by reconcile.",
    )


class ClusteringThresholds(BaseModel):
    """Image-pipeline + clustering knobs (CLAUDE.md §7).

    `max_edge` / `min_coverage` / `merge_delta_e` are consumed by
    `core/image_pipeline.py`; the k-sweep params are consumed by the CALLER to
    construct `adapters/clustering` `KMeansSweep` (which never imports config).
    """

    model_config = _FROZEN

    max_edge: int = Field(
        default=200, ge=16, description="Downscale the longest image edge to this before clustering"
    )
    # --- relevance filter (core/image_pipeline) ---
    min_coverage: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="Drop clusters covering less than this fraction of pixels (after merging)",
    )
    merge_delta_e: float = Field(
        default=3.0, ge=0.0,
        description="Merge centroids within this ΔE76 (just above the ~2.3 JND); "
                    "farther-apart clusters NEVER merge — a checkerboard stays black+white",
    )
    # --- k-means strategy params (used by the caller to build KMeansSweep) ---
    k_max: int = Field(default=6, ge=2, description="Upper end of the k-sweep (k = 2..k_max)")
    solid_delta_e: float = Field(default=2.0, ge=0.0, description="Solid-swatch spread cutoff")
    silhouette_sample: int = Field(default=2000, ge=2, description="Max pixels scored for silhouette")
    seed: int = Field(default=0, description="Fixes all randomness for determinism")


class Thresholds(BaseModel):
    """Top-level tunable config. Compose new nested sections here per workstream."""

    model_config = _FROZEN

    bucketing: BucketingThresholds = BucketingThresholds()
    confidence: ConfidenceThresholds = ConfidenceThresholds()
    clustering: ClusteringThresholds = ClusteringThresholds()


DEFAULT = Thresholds()
