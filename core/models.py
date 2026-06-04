"""Shared domain types + the color record schema (CLAUDE.md §8).

This file is the project's data contract — lock it early (§14), because every
workstream (bucketing, CV pipeline, name analysis, mock data layer, search)
depends on it. pydantic models throughout; field `description=`s double as
per-field instructions when a model is handed to the LLM as a JSON schema.

IMPLEMENTED here: the value types needed by the bucketing + clustering seam
(`ColorBucket`, `HSL`, `LabColor`, `ClusterResult`). The larger records below
are owned by their respective workstreams and left as TODO.

COORDINATION: `ClusterResult` lives HERE (the data contract), and
`ports/clustering.py` + the k-means/HDBSCAN adapters import it from this module
rather than redefine it, so bucketing and clustering agree on one shape. It is a
plain frozen dataclass (not pydantic) with `lab` as a (L, a, b) tuple, so numpy
never leaks into core/ via this type.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ClusterResult:
    """One dominant color from a ClusteringStrategy, BEFORE the relevance filter.

    A lightweight frozen dataclass (not pydantic): it's the per-cluster CV
    interchange type, produced in a hot path and consumed by both the relevance
    filter and `core/buckets.py`. `lab` is a plain tuple so numpy stays out of
    core/. The relevance filter (coverage threshold + ΔE merge) runs downstream
    in core/image_pipeline.py — strategies report everything they find.
    """

    lab: tuple[float, float, float]
    """CIELAB centroid. L in [0, 100]; a/b roughly in [-128, 128]."""

    coverage: float
    """Fraction of the image's pixels in this cluster, in [0, 1]."""


Source = Literal["name", "image", "reconciled", "manual"]

# TODO (data/source workstream): MaterialRecord — one already-persisted row to
#   classify (material_id, optional swatch name, optional R2 key / mock path).
# TODO (name workstream): NameAnalysisResult — bucket(s) + confidence (0-1).
# TODO (CV workstream): ImageAnalysisResult — surviving centroids + their buckets.
# TODO (reconcile workstream): ColorRecord — the full §8 output record
#   (material_id, swatch_id?, source, color_groups: list[ColorBucket],
#    canonical_hsl, lab_centroids, coverage, confidence, needs_review,
#    conflict_reason?). Keep sink-agnostic.
