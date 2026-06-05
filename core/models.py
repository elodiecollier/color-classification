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


# --- INPUT: one already-persisted row to classify --------------------------
class MaterialRecord(BaseModel):
    """One record to classify, mirroring a persisted Directus row.

    PROVISIONAL shape — confirmed once we have a real `company_colors` sample
    (CLAUDE.md §16). Fixtures must match whatever this becomes.
    """

    model_config = _FROZEN

    material_id: str = Field(description="Stable id of the material/product record")
    swatch_id: str | None = Field(default=None, description="Id of the specific swatch, if any")
    swatch_name: str | None = Field(
        default=None, description="Manufacturer's color name, e.g. 'Fall River Glaze'"
    )
    company: str | None = Field(
        default=None, description="Manufacturer name — context for name analysis"
    )
    image_ref: str | None = Field(
        default=None, description="Swatch image reference: R2 key (real) or local path (mock)"
    )


# --- INTERMEDIATE: per-signal analysis results -----------------------------
class NameAnalysisResult(BaseModel):
    """Gemini's read of the swatch NAME (CLAUDE.md §6 step 1)."""

    model_config = _FROZEN

    buckets: list[ColorBucket] = Field(
        default_factory=list, description="Bucket(s) the name maps to; empty if none/unsure"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="0-1; below the config floor counts as 'not intuitive'"
    )


class VisionAnalysisResult(BaseModel):
    """Gemini-vision's ADVISORY read of the swatch image (§3 amendment).

    Same shape as the name signal: bucket votes + confidence. Used only to
    break name-vs-image conflicts in reconcile — never as the color
    measurement (that stays with the deterministic clustering pipeline)."""

    model_config = _FROZEN

    buckets: list[ColorBucket] = Field(
        default_factory=list, description="Bucket(s) the model sees; empty if unsure"
    )
    confidence: float = Field(ge=0.0, le=1.0)


class ImageAnalysisResult(BaseModel):
    """The deterministic image pipeline's output (CLAUDE.md §6 step 2)."""

    model_config = _FROZEN

    buckets: list[ColorBucket] = Field(
        default_factory=list, description="Surviving centroids' buckets, coverage-ordered"
    )
    centroids: list[ClusterResult] = Field(
        default_factory=list,
        description="Surviving LAB centroids + coverage (post relevance-filter)",
    )
    canonical_hsl: HSL | None = Field(
        default=None, description="HSL of the dominant (highest-coverage) centroid"
    )


# --- OUTPUT: the sink-agnostic color record (CLAUDE.md §8) ------------------
class ColorRecord(BaseModel):
    """The enriched result written to the sink (local file now, Directus later)."""

    model_config = _FROZEN

    material_id: str
    swatch_id: str | None = None
    source: Source = Field(description="Which signal produced this result")
    color_groups: list[ColorBucket] = Field(default_factory=list)
    canonical_hsl: HSL | None = None
    lab_centroids: list[ClusterResult] = Field(
        default_factory=list,
        description="Durable raw centroids — kept even now for future similar-color search (§4)",
    )
    coverage: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Fraction of the swatch explained by color_groups; None for name-only",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool = False
    conflict_reason: str | None = Field(
        default=None, description="Set only when name and image disagree (§6 step 3)"
    )


# --- SEARCH / API: the front-end contract (UI builds against this) ----------
# Served by the search demo, e.g. GET /search?color=green -> SearchResponse.
class SearchResultItem(BaseModel):
    """One swatch in a search response — a UI-facing view of a ColorRecord
    joined with display fields from its source MaterialRecord."""

    model_config = _FROZEN

    material_id: str
    swatch_id: str | None = None
    swatch_name: str | None = None
    company: str | None = None
    image_url: str | None = Field(
        default=None, description="Displayable image URL (backend resolves the R2 key/path)"
    )
    color_groups: list[ColorBucket] = Field(default_factory=list)
    canonical_hsl: HSL | None = None
    confidence: float
    needs_review: bool = False


class SearchResponse(BaseModel):
    """Response body for the color-search endpoint."""

    model_config = _FROZEN

    query: str = Field(description="The raw term searched, e.g. 'green'")
    bucket: ColorBucket | None = Field(
        default=None, description="Bucket the term mapped to; None if unmapped"
    )
    count: int
    results: list[SearchResultItem] = Field(default_factory=list)
