"""Demo webapp API + static frontend host — ON the §10 contract.

Data comes from the REAL pipeline (see webapp/db.py):
    1. edit fixtures/records.json (+ drop images in fixtures/images/)
    2. uv run python -m cli.run_batch           # writes output/*.jsonl
    3. uv run uvicorn webapp.main:app --reload  # serves a view over both

The front/back contract (CLAUDE.md §10, types in core/models.py):
  GET    /search?color=<term>            -> SearchResponse

Demo-only admin endpoints (composed strictly from the contract types):
  GET    /api/buckets                    -> the 10-bucket taxonomy
  GET    /api/products                   -> list[SearchResultItem]
  POST   /api/products/{item_id}/tags    -> SearchResultItem   {"tag": "green"}
  DELETE /api/products/{item_id}/tags/{tag} -> SearchResultItem
  GET    /api/review                     -> list[ReviewItem{material, record}]
  POST   /api/review/{item_id}/resolve   -> ColorRecord        {"color_groups": [...]}
  POST   /api/review/{item_id}/dismiss
  POST   /api/classify/{item_id}  (multipart image) -> ColorRecord (live pipeline)

`item_id` is the per-swatch key: swatch_id, falling back to material_id.
Admin mutations are in-memory; restart re-reads the files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adapters.clustering.kmeans_sweep import KMeansSweep
from adapters.clustering.preprocess import load_lab_pixels
from config.thresholds import DEFAULT
from core.buckets import bucket_for_hsl, lab_to_hsl
from core.image_pipeline import analyze_swatch
from core.models import (
    ColorBucket,
    ColorRecord,
    LabColor,
    MaterialRecord,
    SearchResponse,
    SearchResultItem,
    Source,
)
from webapp import db

app = FastAPI(title="Color Classification Demo")


# --- the §10 search contract ---------------------------------------------------


@app.get("/search", response_model=SearchResponse)
def search(color: str = "") -> SearchResponse:
    """Term -> bucket -> published records whose color_groups include it.

    Exact bucket name or synonym only — an unmapped term returns bucket=None
    and zero results (per contract; no fuzzy text fallback)."""
    term = color.strip().lower()
    bucket: ColorBucket | None = None
    if term in db.BUCKETS:
        bucket = ColorBucket(term)
    else:
        bucket = db.SYNONYMS.get(term)

    results: list[SearchResultItem] = []
    if bucket is not None:
        for material in db.MATERIALS:
            record = db.published_for(material)
            if record is not None and bucket in record.color_groups:
                results.append(db.to_search_item(material, record))
    return SearchResponse(query=color, bucket=bucket, count=len(results), results=results)


# --- admin: products + color groups ---------------------------------------------


class TagBody(BaseModel):
    tag: str


@app.get("/api/buckets")
def buckets() -> list[str]:
    return db.BUCKETS


class AdminProduct(BaseModel):
    """Admin-view row: the §10 item + per-bucket detail derived from the record.

    `bucket_coverage` maps EVERY taxonomy bucket -> pixel-coverage share from
    the record's lab_centroids (0.0 when not detected / no centroids). This is
    the per-color evidence behind the tags; `confidence` is the record-level
    value (per §8 there is no per-tag confidence — coverage is the honest
    per-bucket number)."""

    item: SearchResultItem
    source: Source | None = None
    confidence: float = 0.0
    bucket_coverage: dict[str, float]


def _bucket_coverage(record: ColorRecord | None) -> dict[str, float]:
    """Aggregate centroid coverage per bucket, over the full 10-bucket taxonomy."""
    coverage = {b: 0.0 for b in db.BUCKETS}
    if record is not None:
        for c in record.lab_centroids:
            L, a, b_ = c.lab
            lab = LabColor(L=min(max(L, 0.0), 100.0), a=a, b=b_)
            bucket = bucket_for_hsl(lab_to_hsl(lab), DEFAULT.bucketing)
            coverage[bucket.value] = round(coverage[bucket.value] + c.coverage, 3)
    return coverage


@app.get("/api/products", response_model=list[AdminProduct])
def products() -> list[AdminProduct]:
    out = []
    for material in db.MATERIALS:
        record = db.find_record(material)
        out.append(
            AdminProduct(
                item=db.to_search_item(material, record),
                source=record.source if record else None,
                confidence=record.confidence if record else 0.0,
                bucket_coverage=_bucket_coverage(record),
            )
        )
    return out


def _material_or_404(item_id: str) -> MaterialRecord:
    material = db.get_material(item_id)
    if material is None:
        raise HTTPException(404, "no such material/swatch")
    return material


def _bucket_or_422(tag: str) -> ColorBucket:
    try:
        return ColorBucket(tag.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            422, f"'{tag}' is not one of the {len(db.BUCKETS)} color buckets"
        ) from exc


@app.post("/api/products/{item_id}/tags", response_model=SearchResultItem)
def add_tag(item_id: str, body: TagBody) -> SearchResultItem:
    material = _material_or_404(item_id)
    bucket = _bucket_or_422(body.tag)
    key = db.key_of(material.material_id, material.swatch_id)
    record = db.COLOR_RECORDS.get(key)
    if record is None:
        record = ColorRecord(
            material_id=material.material_id, swatch_id=material.swatch_id,
            source="manual", color_groups=[bucket], confidence=1.0,
        )
    elif bucket not in record.color_groups:
        record = record.model_copy(
            update={"color_groups": [*record.color_groups, bucket], "source": "manual"}
        )
    db.COLOR_RECORDS[key] = record
    return db.to_search_item(material, record)


@app.delete("/api/products/{item_id}/tags/{tag}", response_model=SearchResultItem)
def remove_tag(item_id: str, tag: str) -> SearchResultItem:
    material = _material_or_404(item_id)
    bucket = _bucket_or_422(tag)
    key = db.key_of(material.material_id, material.swatch_id)
    record = db.COLOR_RECORDS.get(key)
    if record is not None:
        record = record.model_copy(
            update={"color_groups": [b for b in record.color_groups if b != bucket]}
        )
        db.COLOR_RECORDS[key] = record
    return db.to_search_item(material, record)


# --- admin: review queue ----------------------------------------------------------


class ReviewItem(BaseModel):
    """Queue entry: the flagged ColorRecord + its material's display fields.

    `bucket_coverage` (full 10-bucket map, like AdminProduct's) lets the UI
    offer EVERY bucket for resolution, showing the pixel evidence where it
    exists — a reviewer may pick a color the algorithm didn't suggest."""

    material: MaterialRecord
    record: ColorRecord
    bucket_coverage: dict[str, float]


class ResolveBody(BaseModel):
    color_groups: list[str]


@app.get("/api/review", response_model=list[ReviewItem])
def review_queue() -> list[ReviewItem]:
    items = []
    for record in db.REVIEW_QUEUE:
        material = db.get_material(db.key_of(record.material_id, record.swatch_id))
        if material is not None:
            items.append(ReviewItem(
                material=material, record=record,
                bucket_coverage=_bucket_coverage(record),
            ))
    return items


@app.post("/api/review/{item_id}/resolve", response_model=ColorRecord)
def resolve_review(item_id: str, body: ResolveBody) -> ColorRecord:
    """Human picks the bucket(s) -> record is published (source='manual')."""
    queued = db.get_queued(item_id)
    if queued is None:
        raise HTTPException(404, "no such review item")
    groups = [_bucket_or_422(t) for t in body.color_groups]
    resolved = queued.model_copy(
        update={
            "source": "manual", "color_groups": groups, "confidence": 1.0,
            "needs_review": False, "conflict_reason": None,
        }
    )
    db.REVIEW_QUEUE.remove(queued)
    db.COLOR_RECORDS[item_id] = resolved
    return resolved


@app.post("/api/review/{item_id}/dismiss")
def dismiss_review(item_id: str) -> dict:
    queued = db.get_queued(item_id)
    if queued is None:
        raise HTTPException(404, "no such review item")
    db.REVIEW_QUEUE.remove(queued)
    return {"dismissed": item_id}


# --- classify: the REAL pipeline, live --------------------------------------------


@app.post("/api/classify/{item_id}", response_model=ColorRecord)
async def classify(item_id: str, file: UploadFile) -> ColorRecord:
    """Upload a swatch image -> the real image pipeline -> a §8 ColorRecord.

    Same core call as cli/run_batch (analyze_swatch incl. relevance filter);
    image-only here, so the demo rule stands in for §6 reconciliation:
    1-2 buckets -> published, 3+ -> review queue."""
    material = _material_or_404(item_id)
    key = db.key_of(material.material_id, material.swatch_id)

    image_bytes = await file.read()
    image_result = analyze_swatch(
        image_bytes, load_pixels=load_lab_pixels, strategy=_strategy(), config=DEFAULT,
    )
    if image_result is None:
        raise HTTPException(400, "not a decodable image (or no usable color)")

    ambiguous = len(image_result.buckets) > 2
    record = ColorRecord(
        material_id=material.material_id,
        swatch_id=material.swatch_id,
        source="image",
        color_groups=image_result.buckets,
        canonical_hsl=image_result.canonical_hsl,
        lab_centroids=image_result.centroids,  # the durable §4 asset — always kept
        coverage=round(min(sum(c.coverage for c in image_result.centroids), 1.0), 3),
        confidence=0.4 if ambiguous else DEFAULT.confidence.image_only_confidence,
        needs_review=ambiguous,
    )

    if ambiguous:
        existing = db.get_queued(key)
        if existing is not None:
            db.REVIEW_QUEUE.remove(existing)
        db.REVIEW_QUEUE.append(record)
    else:
        db.COLOR_RECORDS[key] = record
    return record


def _strategy() -> KMeansSweep:
    cfg = DEFAULT.clustering
    return KMeansSweep(
        k_max=cfg.k_max, solid_delta_e=cfg.solid_delta_e,
        silhouette_sample=cfg.silhouette_sample, seed=cfg.seed,
    )


# Static mounts LAST so /search and /api/* win. Swatch images are served from
# the fixtures dir (the mock stand-in for R2) — db.to_search_item builds
# image_url against this mount. html=True serves index.html at /.
app.mount("/swatches", StaticFiles(directory="fixtures/images"), name="swatches")
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
