"""Demo webapp API + static frontend host.

Run:    uv run uvicorn webapp.main:app --reload
Open:   http://localhost:8000

Endpoints (all JSON, all unauthenticated — demo only):
  GET    /api/buckets                      the 10-color taxonomy (for UI chips)
  GET    /api/search?q=green               search demo: term -> bucket -> products
  GET    /api/products                     admin: full table
  POST   /api/products/{id}/tags           admin: add a tag        {"tag": "green"}
  DELETE /api/products/{id}/tags/{tag}     admin: remove a tag
  GET    /api/review                       admin: ambiguous-results queue
  POST   /api/review/{id}/resolve          apply chosen buckets    {"color_groups": [...]}
  POST   /api/review/{id}/dismiss          drop without applying
  POST   /api/classify/{product_id}        upload a swatch image -> REAL pipeline
                                           (preprocess -> k-means -> buckets);
                                           confident -> auto-tag, ambiguous -> queue
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adapters.clustering.kmeans_sweep import KMeansSweep
from adapters.clustering.preprocess import load_lab_pixels
from core.buckets import bucket_for_hsl, buckets_for_centroids, lab_to_hsl
from core.models import ClusterResult, LabColor
from webapp import db

app = FastAPI(title="Color Classification Demo")


# --- search ------------------------------------------------------------------


@app.get("/api/buckets")
def buckets() -> list[str]:
    return db.BUCKETS


@app.get("/api/search")
def search(q: str = "") -> dict:
    """Term -> bucket -> products whose tags include it (CLAUDE.md §10).

    Resolution order: exact bucket name -> synonym map -> plain substring
    match on name/company/tags (so 'fall river' still finds the product).
    """
    term = q.strip().lower()
    if not term:
        return {"query": q, "bucket": None, "matched_via": None, "products": []}

    bucket = term if term in db.BUCKETS else db.SYNONYMS.get(term)
    if bucket:
        hits = [p for p in db.PRODUCTS if bucket in p["tags"]]
        via = "bucket" if term in db.BUCKETS else "synonym"
        return {"query": q, "bucket": bucket, "matched_via": via, "products": hits}

    hits = [
        p for p in db.PRODUCTS
        if term in p["name"].lower()
        or term in p["company"].lower()
        or any(term in t for t in p["tags"])
    ]
    return {"query": q, "bucket": None, "matched_via": "text", "products": hits}


# --- admin: products + tags ---------------------------------------------------


class TagBody(BaseModel):
    tag: str


@app.get("/api/products")
def products() -> list[dict]:
    return db.PRODUCTS


@app.post("/api/products/{product_id}/tags")
def add_tag(product_id: int, body: TagBody) -> dict:
    product = db.get_product(product_id)
    if product is None:
        raise HTTPException(404, "no such product")
    tag = body.tag.strip().lower()
    if not tag:
        raise HTTPException(422, "empty tag")
    if tag not in product["tags"]:
        product["tags"].append(tag)
    return product


@app.delete("/api/products/{product_id}/tags/{tag}")
def remove_tag(product_id: int, tag: str) -> dict:
    product = db.get_product(product_id)
    if product is None:
        raise HTTPException(404, "no such product")
    product["tags"] = [t for t in product["tags"] if t != tag.lower()]
    return product


# --- admin: review queue --------------------------------------------------------


class ResolveBody(BaseModel):
    color_groups: list[str]


@app.get("/api/review")
def review_queue() -> list[dict]:
    return db.REVIEW_QUEUE


@app.post("/api/review/{item_id}/resolve")
def resolve_review(item_id: int, body: ResolveBody) -> dict:
    item = next((r for r in db.REVIEW_QUEUE if r["id"] == item_id), None)
    if item is None:
        raise HTTPException(404, "no such review item")
    product = db.get_product(item["product_id"])
    if product is not None:
        for tag in body.color_groups:
            if tag in db.BUCKETS and tag not in product["tags"]:
                product["tags"].append(tag)
    db.REVIEW_QUEUE.remove(item)
    return {"resolved": item_id, "product": product}


@app.post("/api/review/{item_id}/dismiss")
def dismiss_review(item_id: int) -> dict:
    item = next((r for r in db.REVIEW_QUEUE if r["id"] == item_id), None)
    if item is None:
        raise HTTPException(404, "no such review item")
    db.REVIEW_QUEUE.remove(item)
    return {"dismissed": item_id}


# --- classify: the REAL pipeline, live -----------------------------------------


@app.post("/api/classify/{product_id}")
async def classify(product_id: int, file: UploadFile) -> dict:
    """Upload a swatch image -> preprocess -> k-means -> color buckets.

    Demo confidence rule (deliberately crude — the real one is the §6
    reconciliation): 1-2 buckets = confident, auto-applied as tags;
    3+ buckets = ambiguous, parked in the review queue instead.
    """
    product = db.get_product(product_id)
    if product is None:
        raise HTTPException(404, "no such product")

    pixels = load_lab_pixels(await file.read())
    if pixels is None:
        raise HTTPException(400, "not a decodable image")

    clusters = KMeansSweep().cluster(pixels)
    # Bridge the port's tuple-based ClusterResult to the core/models one.
    # TODO: unify on core.models.ClusterResult per its coordination note.
    core_clusters = [
        ClusterResult(
            centroid=LabColor(L=min(max(c.lab[0], 0.0), 100.0), a=c.lab[1], b=c.lab[2]),
            coverage=c.coverage,
        )
        for c in clusters
    ]
    groups = [str(b) for b in buckets_for_centroids(core_clusters)]
    detail = [
        {
            "bucket": str(bucket_for_hsl(lab_to_hsl(c.centroid))),
            "css": _css(c.centroid),
            "coverage": round(c.coverage, 3),
        }
        for c in core_clusters
    ]

    confident = 0 < len(groups) <= 2
    review_id = None
    if confident:
        for tag in groups:
            if tag not in product["tags"]:
                product["tags"].append(tag)
    else:
        item = db.add_review_item(
            product_id,
            reason=f"Image clustering produced {len(groups)} candidate buckets — too ambiguous to auto-tag.",
            suggested=detail,
        )
        review_id = item["id"]

    return {
        "product_id": product_id,
        "color_groups": groups,
        "clusters": detail,
        "applied": confident,
        "review_id": review_id,
    }


def _css(lab: LabColor) -> str:
    """LAB centroid -> a CSS color string the frontend can render directly."""
    hsl = lab_to_hsl(lab)
    return f"hsl({hsl.h:.0f} {hsl.s * 100:.0f}% {hsl.l * 100:.0f}%)"


# Static frontend — mounted LAST so /api/* wins. html=True serves index.html at /.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
