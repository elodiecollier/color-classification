"""Shared domain types + the color record schema (CLAUDE.md §8).

This file is the project's data contract — lock it early (§14), because every
workstream (bucketing, CV pipeline, name analysis, mock data layer, search)
depends on it. pydantic models throughout; field `description=`s double as
per-field instructions when a model is handed to the LLM as a JSON schema.

IMPLEMENTED here: the value types needed by the bucketing + clustering seam
(`ColorBucket`, `HSL`, `LabColor`, `ClusterResult`). The larger records below
are owned by their respective workstreams and left as TODO.

COORDINATION: `ClusterResult` lives HERE (the data contract), not in
`ports/clustering.py`. The clustering port + the k-means/HDBSCAN adapters should
IMPORT it from this module rather than redefine it, so bucketing and clustering
agree on one shape.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True)


class ColorBucket(StrEnum):
    """The fixed 10-value color taxonomy (§5). A StrEnum so out-of-taxonomy
    values are unrepresentable — LLM/CV output must map onto exactly these."""

    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PURPLE = "purple"
    GREY = "grey"
    WHITE = "white"
    BLACK = "black"
    BROWN = "brown"


class HSL(BaseModel):
    """A single color in HSL. Hue in degrees; saturation/lightness in [0, 1]."""

    model_config = _FROZEN

    h: float = Field(ge=0.0, le=360.0, description="Hue in degrees [0, 360]")
    s: float = Field(ge=0.0, le=1.0, description="Saturation [0, 1]")
    l: float = Field(ge=0.0, le=1.0, description="Lightness [0, 1]")


class LabColor(BaseModel):
    """A single color in CIELAB (the space clustering and ΔE math operate in)."""

    model_config = _FROZEN

    L: float = Field(ge=0.0, le=100.0, description="Lightness [0, 100]")
    a: float = Field(description="Green(-) to red(+) axis")
    b: float = Field(description="Blue(-) to yellow(+) axis")


class ClusterResult(BaseModel):
    """One pixel cluster from the clustering strategy (pre relevance-filter):
    its LAB centroid and the fraction of pixels it covers."""

    model_config = _FROZEN

    centroid: LabColor
    coverage: float = Field(ge=0.0, le=1.0, description="Pixel-share of this cluster [0, 1]")


Source = Literal["name", "image", "reconciled", "manual"]

# TODO (data/source workstream): MaterialRecord — one already-persisted row to
#   classify (material_id, optional swatch name, optional R2 key / mock path).
# TODO (name workstream): NameAnalysisResult — bucket(s) + confidence (0-1).
# TODO (CV workstream): ImageAnalysisResult — surviving centroids + their buckets.
# TODO (reconcile workstream): ColorRecord — the full §8 output record
#   (material_id, swatch_id?, source, color_groups: list[ColorBucket],
#    canonical_hsl, lab_centroids, coverage, confidence, needs_review,
#    conflict_reason?). Keep sink-agnostic.
