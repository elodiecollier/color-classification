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

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adapters.clustering.kmeans_sweep import KMeansSweep
from adapters.clustering.preprocess import load_lab_pixels
from config.thresholds import DEFAULT
from core.buckets import bucket_for_hsl, lab_to_hsl
from core.image_pipeline import analyze_swatch
from core.name_analysis import analyze_name
from core.reconcile import reconcile
from core.search import rank_search
from core.vision_analysis import analyze_image_vision
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


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Never let the browser cache the demo UI files — a stale app.js against a
    fresh index.html produces baffling null-element errors after every change."""
    response = await call_next(request)
    if request.url.path in ("/", "/index.html", "/app.js", "/style.css"):
        response.headers["Cache-Control"] = "no-store"
    return response


# --- the §10 search contract ---------------------------------------------------


SEARCH_PAGE_SIZE = 24
SEARCH_MAX_LIMIT = 200


@app.get("/search", response_model=SearchResponse)
def search(
    color: str = "", groups: str = "", offset: int = 0, limit: int = SEARCH_PAGE_SIZE
) -> SearchResponse:
    """Term -> ranked published records matching by color and/or name/company.

    Paginated: returns results[offset : offset+limit] plus `total` (the full
    match count) so the client can infinite-scroll. Built as if the library
    were huge — the full match set is computed then sliced server-side.

    Empty query = browse: every swatch in the library (bucket=None) so the
    page is never blank. A non-empty term matches a swatch by COLOR (its bucket,
    via exact name or synonym, is in color_groups) and/or by STRING (the term
    appears in the swatch name or company). Results are ranked best-color-match
    then string-match — see `core.search.rank_search`. Review-queue swatches are
    included but match by name/company only (badged ⚠ review in the UI).

    `groups` is an optional comma-separated list of bucket names; when present,
    results are filtered to swatches in ANY of those buckets (a shopping-style
    color facet, applied on top of the query — browse or search alike)."""
    term = color.strip()
    bucket: ColorBucket | None = None
    matches: list[SearchResultItem] = []

    if not term:
        matches = [db.to_search_item(m, db.published_for(m)) for m in db.MATERIALS]
    else:
        # Candidates = published OR pending-review records; rank_search only lets
        # the review ones match by name/company, never by color.
        pairs = [(m, r) for m in db.MATERIALS if (r := db.find_record(m)) is not None]
        bucket, ranked = rank_search(term, pairs)
        matches = [db.to_search_item(material, record) for material, record in ranked]

    # Color facet: keep swatches bucketed in ANY selected color (OR). Unknown
    # bucket names are ignored so a stale/garbage param can't empty the results.
    selected = {g for g in groups.split(",") if g in db.BUCKETS}
    if selected:
        matches = [it for it in matches if any(b in selected for b in it.color_groups)]

    limit = max(1, min(limit, SEARCH_MAX_LIMIT))
    offset = max(0, offset)
    page = matches[offset : offset + limit]
    return SearchResponse(
        query=color, bucket=bucket, count=len(page), total=len(matches),
        offset=offset, limit=limit, results=page,
    )


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


# --- add a new swatch to the library, live (analyze -> human edit -> commit) -------

load_dotenv()  # OPENROUTER_API_KEY for the name signal, if present
_llm_client = None


def _llm():
    """Lazily build the OpenRouter client; None when no key is configured —
    the upload flow then degrades gracefully to image-only."""
    global _llm_client
    if _llm_client is None and os.environ.get("OPENROUTER_API_KEY"):
        from adapters.llm.openrouter import OpenRouterClient
        _llm_client = OpenRouterClient()
    return _llm_client


class UploadAnalysis(BaseModel):
    """Proposed (NOT stored) classification of an uploaded swatch: the full
    pipeline result + the evidence the UI needs for editing."""

    record: ColorRecord  # provisional ids; reconcile's verdict
    bucket_coverage: dict[str, float]
    name_used: bool  # False when no name given or no API key
    name_buckets: list[ColorBucket] = []
    name_confidence: float = 0.0
    vision_used: bool = False  # third opinion runs ONLY on name-vs-image conflicts
    vision_buckets: list[ColorBucket] = []
    vision_confidence: float = 0.0


@app.post("/api/swatches/analyze", response_model=UploadAnalysis)
async def analyze_upload(file: UploadFile, name: str = Form("")) -> UploadAnalysis:
    """Run the REAL two-signal pipeline (image clustering + Gemini name
    analysis + reconcile) on an upload, without storing anything. The UI shows
    this proposal for human edit, then commits via POST /api/swatches."""
    image_bytes = await file.read()
    image_result = analyze_swatch(
        image_bytes, load_pixels=load_lab_pixels, strategy=_strategy(), config=DEFAULT,
    )
    if image_result is None:
        raise HTTPException(400, "not a decodable image (or no usable color)")

    swatch_name = name.strip()
    name_result = None
    client = _llm()
    if client is not None and swatch_name:
        name_result = analyze_name(swatch_name, client)

    provisional = MaterialRecord(material_id="(preview)", swatch_name=swatch_name or None)
    record = reconcile(provisional, name_result, image_result)

    # §3 amendment: on a name-vs-image conflict, get the vision third opinion
    # and re-reconcile with it (it may break the tie toward the image).
    vision_result = None
    if record.conflict_reason and client is not None:
        vision_result = analyze_image_vision(
            image_bytes, client, mime_type=file.content_type or "image/png"
        )
        record = reconcile(
            provisional, name_result, image_result, vision_result=vision_result
        )

    return UploadAnalysis(
        record=record,
        bucket_coverage=_bucket_coverage(record),
        name_used=name_result is not None,
        name_buckets=name_result.buckets if name_result else [],
        name_confidence=name_result.confidence if name_result else 0.0,
        vision_used=vision_result is not None,
        vision_buckets=vision_result.buckets if vision_result else [],
        vision_confidence=vision_result.confidence if vision_result else 0.0,
    )


@app.post("/api/swatches", response_model=ColorRecord)
async def add_swatch(
    file: UploadFile,
    name: str = Form(""),
    record: str | None = Form(None),
    color_groups: str | None = Form(None),
) -> ColorRecord:
    """'Add to library': store an uploaded swatch in the in-memory library.

    Preferred path: `record` (the /analyze proposal, JSON) + `color_groups`
    (the human-confirmed buckets, JSON list) -> published as confirmed.
    Without them (bare API use), falls back to auto image-only classify."""
    image_bytes = await file.read()

    if record is None or color_groups is None:
        # bare path: classify image-only and auto-store (ambiguous -> review)
        image_result = analyze_swatch(
            image_bytes, load_pixels=load_lab_pixels, strategy=_strategy(), config=DEFAULT,
        )
        if image_result is None:
            raise HTTPException(400, "not a decodable image (or no usable color)")
        material = db.add_uploaded_swatch(
            name.strip(), image_bytes, file.content_type or "image/png"
        )
        return _store_image_record(material, image_result)

    # commit path: human reviewed the /analyze proposal
    try:
        proposal = ColorRecord.model_validate_json(record)
        groups = [_bucket_or_422(t) for t in json.loads(color_groups)]
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, f"bad record/color_groups payload: {exc}") from exc
    if not groups:
        raise HTTPException(422, "select at least one color group")

    material = db.add_uploaded_swatch(
        name.strip(), image_bytes, file.content_type or "image/png"
    )
    edited = set(groups) != set(proposal.color_groups)
    final = proposal.model_copy(
        update={
            "material_id": material.material_id,
            "swatch_id": material.swatch_id,
            "color_groups": groups,
            # human confirmed -> publish; an edit makes it a manual call
            "source": "manual" if edited else proposal.source,
            "needs_review": False,
            "conflict_reason": None,
        }
    )
    db.COLOR_RECORDS[db.key_of(material.material_id, material.swatch_id)] = final
    return final


@app.get("/uploads/{key}")
def uploaded_image(key: str) -> Response:
    """Serve a live-uploaded swatch image from memory (see db.UPLOADED_IMAGES)."""
    entry = db.UPLOADED_IMAGES.get(key)
    if entry is None:
        raise HTTPException(404, "no such upload")
    data, content_type = entry
    return Response(content=data, media_type=content_type)


# --- classify: the REAL pipeline, live --------------------------------------------


@app.post("/api/classify/{item_id}", response_model=ColorRecord)
async def classify(item_id: str, file: UploadFile) -> ColorRecord:
    """Upload a swatch image -> the real image pipeline -> a §8 ColorRecord.

    Same core call as cli/run_batch (analyze_swatch incl. relevance filter);
    image-only here, so the demo rule stands in for §6 reconciliation:
    1-2 buckets -> published, 3+ -> review queue."""
    material = _material_or_404(item_id)

    image_bytes = await file.read()
    image_result = analyze_swatch(
        image_bytes, load_pixels=load_lab_pixels, strategy=_strategy(), config=DEFAULT,
    )
    if image_result is None:
        raise HTTPException(400, "not a decodable image (or no usable color)")
    return _store_image_record(material, image_result)


def _store_image_record(material: MaterialRecord, image_result) -> ColorRecord:
    """Build the §8 record from an image analysis and store it: confident
    (1-2 buckets) -> published, ambiguous (3+) -> review queue."""
    key = db.key_of(material.material_id, material.swatch_id)
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
