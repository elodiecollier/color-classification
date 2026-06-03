"""Shared domain types + the color record schema (CLAUDE.md §8).

This file is the project's data contract — lock it early (§14), because every
workstream (bucketing, CV pipeline, name analysis, mock data layer, search)
depends on it. pydantic models throughout; field `description=`s double as
per-field instructions when a model is handed to the LLM as a JSON schema.

Will define:

VALUE TYPES
  - ColorBucket: the fixed 10-value taxonomy from §5 —
    red, orange, yellow, green, blue, purple, grey, white, black, brown.
    A Literal/StrEnum so out-of-taxonomy values are unrepresentable.
  - HSL / LabColor: small value objects for canonical_hsl and lab_centroids.
  - Source: Literal["name", "image", "reconciled", "manual"].

INPUT SHAPE
  - MaterialRecord: one already-persisted row to classify —
    material_id, optional swatch name, optional swatch image reference
    (R2 key / mock path). Mirrors the real row shape; fixtures must match it.

INTERMEDIATE RESULTS
  - NameAnalysisResult: bucket(s) + confidence (0-1) from the Gemini call.
  - ImageAnalysisResult: surviving LAB centroids with coverage %, plus the
    bucket(s) they map to.

OUTPUT (the §8 record, sink-agnostic)
  - ColorRecord:
      material_id, optional swatch_id, source,
      color_groups: list[ColorBucket]   (a swatch can be MULTIPLE colors),
      canonical_hsl,
      lab_centroids                     (REQUIRED even now — durable asset
                                         for future "similar color" search;
                                         survives taxonomy re-tuning),
      coverage, confidence,
      needs_review, conflict_reason     (conflict_reason only on conflicts).
"""
