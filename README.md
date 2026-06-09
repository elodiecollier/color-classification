# color-classification

Enrich Acelab materials with **standard color classifications** — figure out the
real color(s) of each swatch (whose names are often non-intuitive, like
*"Fall River Glaze"*) — and demo searching them by color (type *"green"*, get
swatches that map to green like sage / lime / forest).

**Extraction** is the bulk of the work (Gemini for intuitive swatch *names*,
deterministic LAB/HSL clustering for swatch *images*). **Search** is a thin demo
over a fixed set of color buckets, with a small web UI on top.

Built **standalone against a mocked data layer** first, to be integrated into
Acelab's Directus + ingestion pipeline once proven.

## Contributors / AI agents start here

📖 **Read [`CLAUDE.md`](./CLAUDE.md)** — the canonical context: the problem, the
division of labor (LLM for language, math for perceptual color), the color
buckets, the per-record flow, schema, build order, and open questions. It's
auto-loaded by Claude Code so every session shares the same context.

## Quick start

```bash
uv run pytest                                # the test suite (93)
uv run python -m cli.run_batch               # classify fixtures -> output/*.jsonl (image-only)
uv run python -m cli.run_batch --with-name   # + Gemini name signal (OPENROUTER_API_KEY in .env)
uv run python -m cli.run_batch --with-name --with-vision  # + Gemini-vision tiebreak on name-vs-image conflicts only
uv run python -m cli.eval                    # accuracy harness over labelled swatches
uv run uvicorn webapp.main:app --reload      # demo webapp -> http://localhost:8000
```

The webapp loads `fixtures/records.json` + `output/*.jsonl` **at startup** —
restart it after a batch run. To add data: append rows to `fixtures/records.json`
(same `material_id` + different `swatch_id` = multiple swatches per material),
drop images in `fixtures/images/`, re-run the batch.

## Data contracts

These types are the seams between all workstreams — **change them only by team
agreement** (CLAUDE.md §14). Everything below lives in
[`core/models.py`](./core/models.py) unless noted otherwise.

### How they flow

```
MaterialRecord ──(swatch name)──▶ NameAnalysisResult ──┐
      │                                                ├─ reconcile ─▶ ColorRecord ─▶ sink / search
      └──(swatch image)─▶ [ClusterResult…] ─▶ ImageAnalysisResult ──┘
                          (ClusteringStrategy)

GET /search?color=<term> ─▶ SearchResponse{ results: [SearchResultItem…] }
```

### Value types (the vocabulary)

| Type | What it is | Notes |
|---|---|---|
| **`ColorBucket`** | The fixed 10-color taxonomy: `red orange yellow green blue purple grey white black brown` (CLAUDE.md §5). | A `StrEnum`, so out-of-taxonomy values are *unrepresentable* — anything an LLM or the CV pipeline produces must map onto exactly these. Search is a lookup over these buckets. |
| **`HSL`** | One color as hue (degrees, 0–360) + saturation/lightness (0–1). | The space the *bucketing rules* operate in (`core/buckets.py`), and what the UI renders color chips from. |
| **`LabColor`** | One color in CIELAB (`L` 0–100, `a`/`b` ≈ ±128). | The *perceptual* space: Euclidean distance ≈ how different two colors look (ΔE). Clustering and ΔE merging happen here. |
| **`ClusterResult`** | One dominant color found in a swatch image: `lab` (an `(L, a, b)` tuple) + `coverage` (fraction of pixels, 0–1). | The CV interchange type, produced by a `ClusteringStrategy`, *before* the relevance filter. A frozen dataclass with a plain tuple so numpy never leaks into `core/`. **Single source of truth is `core/models.py`** — `ports/clustering.py` re-exports it. |
| **`Source`** | Where a classification came from: `"name" \| "image" \| "reconciled" \| "manual"`. | Lets every record say which signal produced it. |

### Pipeline records (input → intermediate → output)

| Type | What it is | Notes |
|---|---|---|
| **`MaterialRecord`** | INPUT — one already-persisted row to classify: `material_id`, optional `swatch_id` / `swatch_name` / `company` / `image_ref` (R2 key real, local path mock). | Shape is *provisional* until we see a real `company_colors` sample (§16). Fixtures must match it. |
| **`NameAnalysisResult`** | INTERMEDIATE — Gemini's read of the swatch *name*: `buckets` + `confidence` (0–1). | Below the config confidence floor = "name not intuitive" → fall through to the image (§6 step 1). |
| **`ImageAnalysisResult`** | INTERMEDIATE — the deterministic image pipeline's output: surviving `centroids` (`ClusterResult`s post relevance-filter), their `buckets` (coverage-ordered), and `canonical_hsl` (dominant centroid). | The image signal is *authoritative* when a swatch image exists (§4). |
| **`ColorRecord`** | OUTPUT — the §8 enriched record written to the sink: `source`, `color_groups` (list — a swatch can be multiple colors), `canonical_hsl`, `lab_centroids`, `coverage`, `confidence`, `needs_review`, `conflict_reason`. | Sink-agnostic (local file now, Directus later). `lab_centroids` is **always kept** — it's the durable asset for future similar-color search and survives taxonomy re-tuning (§4). The **review queue is just `ColorRecord`s with `needs_review=True`**; `conflict_reason` is set only when name and image disagree (§6 step 3). |

### Search / UI contract (CLAUDE.md §10)

| Type | What it is | Notes |
|---|---|---|
| **`SearchResultItem`** | One swatch in a search response — a UI-facing view of a `ColorRecord` *joined* with display fields from its `MaterialRecord` (`swatch_name`, `company`, `image_url`). | `canonical_hsl` lets the UI render a chip before real swatch images are wired. |
| **`SearchResponse`** | The body of `GET /search?color=<term>`: `query`, the `bucket` the term mapped to (`null` if unmapped), `count`, `results`. | **This is the front/back seam** — the UI builds against this and nothing else. Served by `webapp/main.py`; results are ranked by color match then swatch-name/company text match (`core.search.rank_search`), so an unmapped term can still return text matches with `bucket: null`. Review-queue swatches match by name/company only. |

### Interfaces & config (not in `core/models.py`)

| Type | Where | What it is |
|---|---|---|
| **`ClusteringStrategy`** | `ports/clustering.py` | Protocol for the swappable pixel-clusterer: `cluster(lab_pixels: (N,3) ndarray) -> list[ClusterResult]`, coverage-sorted, deterministic. Implemented by `adapters/clustering/kmeans_sweep.py` (k-sweep + silhouette); HDBSCAN is the planned A/B. Acid test: a black/white checkerboard must yield **two** clusters, never one grey. |
| **`RecordSource` / `ImageStore` / `ColorSink`** | `ports/` | The integration seams (read records / fetch image bytes / write `ColorRecord`s). Implemented by `adapters/mock/*` (fixture source, local images, JSONL sink + `jsonl_color_source` reader); Directus/R2 swap in later, `core/` unchanged. |
| **`LLMClient`** | `ports/llm.py` | The name-analysis LLM seam: `complete_json(system, user) -> str`. Implemented by `adapters/llm/openrouter.py` (OpenRouter → Gemini flash, `openai` SDK); `core/name_analysis` takes it injected, so tests use a fake. |
| **`Thresholds`** (`.bucketing` / `.clustering` / `.confidence`) | `config/thresholds.py` | THE single tunable-config constant (`DEFAULT`): hue bands, achromatic cutoffs, the brown rule, ΔE merge/coverage filters, and the reconcile confidence table. Every boundary number in the system lives here — nothing is hard-coded elsewhere (§5). |
| **`ReviewItem` / `AdminProduct`** | `webapp/main.py` | Demo-only compositions for the admin UI: the contract types side by side plus a derived `bucket_coverage` map (per-bucket pixel coverage computed from `lab_centroids`) — evidence display, not a new contract. |

## Status

**End-to-end complete, running on real data** — the full two-signal pipeline
(Gemini name analysis + LAB clustering + reconcile) has classified a 22-swatch
real manufacturer set, with agreements at 95%, non-intuitive names correctly
falling through to pixels, and name-vs-image conflicts routed to the review
queue. The demo webapp serves that output: color search, an admin view with
per-bucket pixel-coverage evidence, full-taxonomy review resolution with swatch
thumbnails, and drag-and-drop live classification. 93 tests pass.

**Current focus: threshold tuning** against the measured real-data misses
(light wood → orange, ivory → yellow, olive ↔ brown — see `CLAUDE.md` §16),
including the neutral/beige-bucket decision. Then Phase 4: Directus/R2 adapters
behind the existing ports. See `CLAUDE.md` §13/§18 for the live plan.
