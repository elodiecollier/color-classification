"""Demo webapp API + static frontend host — ON the §10 contract.

Run:    uv run uvicorn webapp.main:app --reload
Open:   http://localhost:8000

The front/back contract (CLAUDE.md §10, types in core/models.py):
  GET    /search?color=<term>            -> SearchResponse

Demo-only admin endpoints (not part of the §10 contract, but composed strictly
from the contract types — SearchResultItem / MaterialRecord / ColorRecord):
  GET    /api/buckets                    -> the 10-bucket taxonomy
  GET    /api/products                   -> list[SearchResultItem]
  POST   /api/products/{mid}/tags        -> SearchResultItem   {"tag": "green"}
  DELETE /api/products/{mid}/tags/{tag}  -> SearchResultItem
  GET    /api/review                     -> list[ReviewItem{material, record}]
  POST   /api/review/{mid}/resolve       -> ColorRecord        {"color_groups": [...]}
  POST   /api/review/{mid}/dismiss
  POST   /api/classify/{mid}  (multipart image) -> ColorRecord
         runs the REAL pipeline (preprocess -> k-means -> buckets); confident
         results are published, ambiguous ones land in the review queue.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adapters.clustering.kmeans_sweep import KMeansSweep
from adapters.clustering.preprocess import load_lab_pixels
from core.buckets import buckets_for_centroids, lab_to_hsl
from core.models import (
    ColorBucket,
    ColorRecord,
    LabColor,
    MaterialRecord,
    SearchResponse,
    SearchResultItem,
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
        results = [
            db.to_search_item(m, db.COLOR_RECORDS[m.material_id])
            for m in db.MATERIALS
            if m.material_id in db.COLOR_RECORDS
            and bucket in db.COLOR_RECORDS[m.material_id].color_groups
        ]
    return SearchResponse(query=color, bucket=bucket, count=len(results), results=results)


# --- admin: products + color groups ---------------------------------------------


class TagBody(BaseModel):
    tag: str


@app.get("/api/buckets")
def buckets() -> list[str]:
    return db.BUCKETS


@app.get("/api/products", response_model=list[SearchResultItem])
def products() -> list[SearchResultItem]:
    return [db.to_search_item(m, db.find_record(m.material_id)) for m in db.MATERIALS]


def _material_or_404(material_id: str) -> MaterialRecord:
    material = db.get_material(material_id)
    if material is None:
        raise HTTPException(404, "no such material")
    return material


def _bucket_or_422(tag: str) -> ColorBucket:
    try:
        return ColorBucket(tag.strip().lower())
    except ValueError:
        raise HTTPException(422, f"'{tag}' is not one of the {len(db.BUCKETS)} color buckets")


@app.post("/api/products/{material_id}/tags", response_model=SearchResultItem)
def add_tag(material_id: str, body: TagBody) -> SearchResultItem:
    material = _material_or_404(material_id)
    bucket = _bucket_or_422(body.tag)
    record = db.COLOR_RECORDS.get(material_id)
    if record is None:
        record = ColorRecord(
            material_id=material_id, swatch_id=material.swatch_id,
            source="manual", color_groups=[bucket], confidence=1.0,
        )
    elif bucket not in record.color_groups:
        record = record.model_copy(
            update={"color_groups": [*record.color_groups, bucket], "source": "manual"}
        )
    db.COLOR_RECORDS[material_id] = record
    return db.to_search_item(material, record)


@app.delete("/api/products/{material_id}/tags/{tag}", response_model=SearchResultItem)
def remove_tag(material_id: str, tag: str) -> SearchResultItem:
    material = _material_or_404(material_id)
    bucket = _bucket_or_422(tag)
    record = db.COLOR_RECORDS.get(material_id)
    if record is not None:
        record = record.model_copy(
            update={"color_groups": [b for b in record.color_groups if b != bucket]}
        )
        db.COLOR_RECORDS[material_id] = record
    return db.to_search_item(material, record)


# --- admin: review queue ----------------------------------------------------------


class ReviewItem(BaseModel):
    """Queue entry: the flagged ColorRecord + its material's display fields."""

    material: MaterialRecord
    record: ColorRecord


class ResolveBody(BaseModel):
    color_groups: list[str]


@app.get("/api/review", response_model=list[ReviewItem])
def review_queue() -> list[ReviewItem]:
    return [
        ReviewItem(material=db.get_material(r.material_id), record=r)
        for r in db.REVIEW_QUEUE
        if db.get_material(r.material_id) is not None
    ]


@app.post("/api/review/{material_id}/resolve", response_model=ColorRecord)
def resolve_review(material_id: str, body: ResolveBody) -> ColorRecord:
    """Human picks the bucket(s) -> record is published (source='manual')."""
    queued = db.get_queued(material_id)
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
    db.COLOR_RECORDS[material_id] = resolved
    return resolved


@app.post("/api/review/{material_id}/dismiss")
def dismiss_review(material_id: str) -> dict:
    queued = db.get_queued(material_id)
    if queued is None:
        raise HTTPException(404, "no such review item")
    db.REVIEW_QUEUE.remove(queued)
    return {"dismissed": material_id}


# --- classify: the REAL pipeline, live --------------------------------------------


@app.post("/api/classify/{material_id}", response_model=ColorRecord)
async def classify(material_id: str, file: UploadFile) -> ColorRecord:
    """Upload a swatch image -> preprocess -> k-means -> a §8 ColorRecord.

    Demo confidence rule (stands in for the real §6 reconciliation, which needs
    the name signal): 1-2 buckets -> published; 3+ -> review queue."""
    material = _material_or_404(material_id)

    pixels = load_lab_pixels(await file.read())
    if pixels is None:
        raise HTTPException(400, "not a decodable image")

    clusters = KMeansSweep().cluster(pixels)  # sorted by coverage desc
    if not clusters:
        raise HTTPException(400, "empty image")
    groups = buckets_for_centroids(clusters)

    dominant = clusters[0]
    ambiguous = len(groups) > 2
    record = ColorRecord(
        material_id=material_id,
        swatch_id=material.swatch_id,
        source="image",
        color_groups=groups,
        canonical_hsl=lab_to_hsl(_lab_of(dominant.lab)),
        lab_centroids=clusters,  # the durable raw asset (§4) — always kept
        coverage=round(min(sum(c.coverage for c in clusters), 1.0), 3),
        confidence=0.4 if ambiguous else round(dominant.coverage, 2),
        needs_review=ambiguous,
    )

    if ambiguous:
        existing = db.get_queued(material_id)
        if existing is not None:
            db.REVIEW_QUEUE.remove(existing)
        db.REVIEW_QUEUE.append(record)
    else:
        db.COLOR_RECORDS[material_id] = record
    return record


def _lab_of(lab: tuple[float, float, float]) -> LabColor:
    """ClusterResult's (L, a, b) tuple -> LabColor (L clamped to valid range)."""
    L, a, b = lab
    return LabColor(L=min(max(L, 0.0), 100.0), a=a, b=b)


# Static frontend — mounted LAST so /search and /api/* win. html=True serves
# index.html at /.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
