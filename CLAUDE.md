# Color Classification

> Canonical context + plan for this repo. Auto-loaded by Claude Code. Read this
> first — it captures decisions and rationale that aren't recoverable from the
> code alone. Keep it updated as decisions change.
>
> This plan is the **reconciliation of two independent plans** (Elodie's and her
> partner's) for the same project. Where they diverged, the agreed direction is
> recorded below.

## 1. What this repo is

A **standalone** project to build and prove an end-to-end **color enrichment +
search** flow against a **mocked data layer**, then integrate it into Acelab's
existing systems (Directus, the existing ingestion pipeline) once it works.

Building it standalone with mocks deliberately sidesteps external blockers (no
Directus write access needed, no changes to the live pipeline). We classify the
records we **already have** and prove out color search.

**Three parts, very unequal effort:**
- **EXTRACTION** (the overwhelming majority of the work): figure out the standard
  color(s) of each swatch/record.
- **SEARCH** (thin): type "green", get back records that map to green — a small
  bucket lookup over the extracted data.
- **UI** (a demo front-end, now an explicit project goal): a simple web interface
  over the search so the result is showable. Built against the search-API contract
  (§10); it does not block the extraction work. Extraction remains the core goal —
  search + UI are the demo layer that proves it out.

## 2. The problem (why this exists)

- Acelab has a materials database (third-party / **Directus**) with an existing
  ingestion pipeline that discovers product-page images/documents, classifies
  them via **Gemini multimodal extraction**, and persists rows with **R2** keys.
  Images are already classified into `md_file_types` — including **`Swatch`**.
- Current color search is unreliable: it needs **exact swatch-name matches**, but
  names are often non-intuitive (e.g. **"Fall River Glaze"**) and some records
  have no swatch at all.
- Goal: a user searches **"green"** and gets products whose swatches map to green
  (e.g. "sage", "lime", "forest").

This phase adds **color classification as an ENRICHMENT LAYER on top of the
existing pipeline** — not a new ingestion path. DB write-back and inline pipeline
hooks come later.

## 3. Division of labor (the core design principle)

- **Gemini handles LANGUAGE** — "is this swatch *name* intuitively a color?"
  (e.g. "Sage" → green). Reuses the existing Gemini client.
- **Deterministic LAB/HSL math handles PERCEPTUAL color** — extracting the
  dominant color(s) from a swatch *image* via clustering. **Do NOT ask an LLM to
  eyeball dominant colors** — multi-tone / gradient / checkerboard swatches need
  real clustering (a black/white checkerboard must classify as black + white,
  NOT gray).
- **Search is discrete buckets** — classify into a fixed set of color groups;
  search maps the query term to a group and returns its members. No embeddings.

## 4. Key decisions (with rationale)

| Decision | Why |
|---|---|
| **Search = discrete color buckets** (the 10 below), term→group exact match | Simple, self-contained, explainable; directly serves "green → sage/lime"; no embedding infra or external Search API. Search is only a demo. |
| **No embeddings / no external Search API / no OpenRouter** this phase | Not needed once search is buckets. Keeps the repo self-contained. |
| **Extraction: name→Gemini when intuitive, else image→LAB clustering** | Right tool per job: LLM for language, deterministic CV for perceptual color. |
| **Image pipeline is authoritative when a swatch image exists**; name is a cheap pre-check / corroboration | Names lie ("Fall River Glaze"); pixels don't. |
| **Reconcile name vs image; conflicts → review queue** (never silently pick) | Two independent signals cross-checked = trustworthy output + a triage path for hard cases. |
| **Gemini only** (reuse existing client) for the name call | We're standardized on Gemini; don't add a provider abstraction unless fallback is explicitly needed. |
| **Local-file sink now; Directus write-back later**, sink swappable behind an interface | Prove it standalone; integration = swap the adapter, no pipeline changes. |
| **Store raw `lab_centroids` even now** | Durable asset: enables future "similar color" LAB-distance search and survives taxonomy re-tuning. |

> **Superseded:** an earlier draft proposed text-descriptive *embeddings* for
> search and Gemini *vision* for image color. Both were dropped in favor of
> buckets (search) and deterministic LAB clustering (extraction).

## 5. The color buckets (taxonomy)

Ten groups: **red, orange, yellow, green, blue, purple, grey, white, black, brown.**

- **Achromatic check FIRST**: very low saturation, or lightness near 0/100 →
  **black / white / grey**, regardless of hue. (This is what catches each
  checkerboard tile before hue matters.)
- **Brown is a special case** — not a pure hue. It's roughly *orange/red hue +
  low lightness + low/moderate saturation*; check for it **before** falling into
  orange/red.
- Otherwise bucket by **hue**: red, orange, yellow, green, blue, purple. (Cyan
  folds into blue/green; pink folds into red — boundary choices.)
- **All boundaries + thresholds live in ONE config constant**, re-tunable against
  real swatches. Optional light/dark lightness sub-tier, config-gated.
- **Known watch-item:** building materials are full of **beige/tan/cream**
  neutrals; expect them to scatter across white/brown/yellow. Revisit whether a
  neutral bucket is needed once we test on real data.
- A swatch can be **multiple colors** — `color_groups` is a **list**, not one
  value.

## 6. Per-record classification flow

Branch on what each record has:
1. **Has swatch image** (classified `Swatch`, R2 key available) → image pipeline
   is **authoritative**; swatch name (if present) is a cheap pre-check.
2. **Has swatch name but no usable image** → name-only analysis via Gemini.
3. **Has neither** → product-image fallback (STRETCH) or straight to review queue.

Flow:
1. **Name pre-check** (cheap, only when a name exists): Gemini maps name →
   bucket(s) + confidence. Descriptive names ("sage") resolve here; non-intuitive
   names ("Fall River Glaze") return low confidence → fall through to the image.
2. **Image color extraction** (when a swatch image exists): R2 → LAB clustering →
   relevance filter → HSL bucketing. **Authoritative** when present.
3. **Reconcile**: name & image agree → high confidence; conflict (name "blue",
   image "grey") → flag for review, record `conflict_reason`, do NOT silently
   pick one.
4. **No swatch at all** → product-image fallback (stretch) or review queue.

## 7. Image color pipeline (deterministic, swappable)

- Downscale (max ~200px).
- Convert to **CIELAB**.
- **Cluster** pixels: K-means with k-sweep 1..6 + silhouette selection, **or**
  HDBSCAN. Keep the clustering algorithm **swappable behind an interface**.
- Per cluster: centroid color + coverage %.
- **Relevance filter**: keep clusters above a coverage threshold; merge clusters
  within a small ΔE; but **do NOT merge perceptually distant clusters**
  (checkerboard → black + white, not gray).
- Convert surviving centroids LAB → HSL → bucket (per §5).

## 8. Color record schema (local JSONL/CSV; sink-agnostic)

```jsonc
{
  "material_id": "...",
  "swatch_id": "...",            // optional
  "source": "name" | "image" | "reconciled" | "manual",
  "color_groups": [],            // one or more buckets from §5
  "canonical_hsl": {...},
  "lab_centroids": [],           // REQUIRED even now — durable asset for future
                                 // "similar color" distance search; survives re-tuning
  "coverage": 0.0,
  "confidence": 0.0,
  "needs_review": false,
  "conflict_reason": "..."       // present only on conflicts
}
```
Keep the schema clean and the **sink swappable** so a Directus DB writer can
replace the file writer later with no pipeline changes.

## 9. LLM usage

- **Reuse the existing Gemini client** for the name-analysis call only. Do **not**
  introduce a separate provider abstraction (OpenRouter, etc.) this phase.
- Prompt Gemini to return **strict JSON**: `color_group`(s) chosen ONLY from the
  fixed §5 taxonomy + `confidence` 0–1. Parse defensively; parse failure or
  out-of-taxonomy output → treat as low confidence → review queue.
- (Existing pipeline model is cited as `gemini-2.5-flash`; the live extraction
  code uses `gemini-3-flash-preview` — confirm which to use.)

## 10. Search + demo UI

Search is a thin lookup over the buckets; a small web UI makes the result
showable. Both exist to *demonstrate* the extraction.

**Search logic:** map the user's color term → bucket (reuse the name→group
logic), then return all records whose `color_groups` include it, reading from the
output file.

**Search API (the front/back contract).** A minimal FastAPI endpoint —
`GET /search?color=<term>` → `SearchResponse` (defined in `core/models.py`). The
response shape below is what the UI builds against, so the front-end can be
developed in parallel against a stub with zero backend dependency:

```json
{
  "query": "green",
  "bucket": "green",
  "count": 1,
  "results": [
    { "material_id": "m1", "swatch_id": "s1", "swatch_name": "Sage",
      "company": "Acme", "image_url": "https://.../swatch.jpg",
      "color_groups": ["green"], "canonical_hsl": { "h": 120, "s": 0.4, "l": 0.5 },
      "confidence": 0.9, "needs_review": false } ]
}
```

`color_groups` values are always one of the fixed §5 buckets; `canonical_hsl`
lets the UI render a color chip even before real swatch images are wired.

**UI:** a simple front-end that calls the search API and renders results — color
chip from `canonical_hsl`, swatch name, company, image, and a `needs_review`
flag. Keep it minimal; it's a demo, not a product surface.

> **Current state: ALIGNED.** The demo `webapp/` serves exactly this contract:
> `GET /search?color=<term>` → `SearchResponse` (types imported from
> `core/models.py`). Its demo-only admin endpoints (`/api/products`, `/api/review`,
> `/api/classify`) are not part of the contract but are composed strictly from the
> contract types — `SearchResultItem`, `MaterialRecord`, and §8 `ColorRecord`
> (review queue = `ColorRecord`s with `needs_review=True`; classify returns a
> `ColorRecord`). No webapp-local shapes remain.

## 11. Repo layout (intended)

```
color-classification/
  config/                # ALL thresholds: hue boundaries, achromatic cutoffs,
                         # brown rule, ΔE merge distance, coverage %, confidence cutoffs
  core/                  # pure domain — NO external I/O
    buckets.py           # HSL → bucket grouping (§5): achromatic-first, brown rule, hue bands
    image_pipeline.py    # downscale → CIELAB → cluster → relevance filter → centroids → HSL
    name_analysis.py     # Gemini name → bucket(s) + confidence (strict JSON)
    reconcile.py         # name vs image agreement → confidence / conflict → review
    models.py            # the §8 color record schema
    gemini.py            # thin reuse of the existing Gemini client idiom
  ports/                 # the integration seam — interfaces only
    record_source.py     # read persisted records (ids, swatch name?, R2 key)
    color_sink.py        # write color records (file now, Directus later)
    image_store.py       # read swatch image bytes (R2; mock = local files)
    clustering.py        # swappable clustering algorithm
  adapters/
    mock/                # NOW — file sink, local-image store, fixture record source
    r2/  directus/       # LATER — stubs for now
  fixtures/
  cli/
    run_batch.py         # batch over records: 3-way branch, file sink + review queue
    search.py            # term → bucket → records from the output file
  webapp/                # demo API + static UI (partner's lane), FastAPI-served
    main.py              # /api/search, /api/classify (live pipeline), review queue
    db.py                # in-memory mock product table for the demo
    static/              # index.html + app.js + style.css
  tests/
```
Keep `core/` free of external dependencies; all I/O behind `ports/`. Swappable
behind interfaces: the clustering algorithm and the file/DB sink. The demo lives
in `webapp/` (FastAPI + uvicorn serving a static UI) — a thin layer that calls
`core/` + the clustering adapter, fully on the §10/§8 contract types.

## 12. Mocking the data layer (concrete)

We never touch Directus or the live pipeline during development.
- **Record source — persisted records**: `fixtures/*.json` mirroring the real row
  shape (ids, optional swatch name, R2 key), read via `adapters/mock`.
- **Image store — swatch images**: local image files via the mock `image_store`
  (real = R2).
- **Color sink — output**: write `color_groups`/HSL/`lab_centroids` records to a
  local JSONL/CSV file; the review queue is a second file. Directus writer swaps
  in later.

Because each sits behind a port, **integration = writing `adapters/r2/*`,
`adapters/directus/*` against the same interfaces, with `core/` unchanged.**

## 13. Build order (step by step)

Ownership: **[You]** = Elodie (backend: extraction + search) · **[Partner]** =
frontend/UI. (The AI agent is a tool used within either lane.) `✅` = done.

### Phase 0 — Ground & scaffold
1. **[You]** Confirm data inputs (§16): record source/format, whether the swatch
   **name** is queryable this phase, how R2 keys are referenced. Provide a few
   real swatches (name + image) + `GOOGLE_GENAI_API_KEY`. — *open*
2. Scaffold repo + the **one config file**. — ✅
3. **HSL bucketing module** (`buckets.py`), config-driven + synthetic-color tests. — ✅
4. **Shared record + API schema** (`core/models.py`) — the §8/§10 contract every
   lane builds against; `ClusterResult` unified into one type. — ✅

### Phase 1 — Extraction (the bulk) — *You*
5. Clustering: `kmeans_sweep` + `preprocess`. — ✅ (done by partner before UI pivot)
6. **[You]** `core/image_pipeline.py`: relevance filter + wire
   preprocess → cluster → `buckets_for_centroids` → `ImageAnalysisResult`; add the
   clustering/ΔE section of `config/thresholds.py`; `test_image_pipeline.py`.
7. **[You]** `core/gemini.py` + `core/name_analysis.py`: name → bucket +
   confidence (strict JSON); add the confidence section of config.
8. **[You]** `core/reconcile.py`: name vs image agreement → `ColorRecord`.
9. **[You]** Mock data layer: the three ports + `adapters/mock/*` + `fixtures/`.
10. **[You]** `cli/run_batch.py`: records → 3-way branch → image/name → reconcile
    → sink. Then run on real swatches and tune the §5 thresholds.

### Phase 2 — Search + demo UI
11. **[Partner]** the demo `webapp/` — search, admin tags, review queue, and a
    live `/api/classify` that runs the real pipeline. — ✅ built.
12. **[Partner]** align `webapp/` to the §10 `SearchResponse` / §8 `ColorRecord`
    contract. — ✅ done (no webapp-local shapes remain).

### Phase 3 — Tests & eval
13. **[You]** Unit tests across the lanes + an accuracy spot-check on records with
    known colors. **[Partner]** UI sanity once wired to the live API.

### Phase 4 — Integration (later; see §15)
14. **[You]** Resolve Directus write-back + inline-pipeline-hook ownership.
15. **[You]** `adapters/r2/*` + `adapters/directus/*` against the ports; design
    the classify step as a post-persist hook on new `Swatch` rows.

## 14. Parallel workstreams (who can work on what)

The contracts are now locked — the §8 records, the §10 search-API shape, the
ports, and `ClusterResult` — so the two lanes run independently:

| Stream | Owner | Depends on | Status / can start |
|---|---|---|---|
| **Frontend / demo UI** (`webapp/`) | Partner | §10 shape | ✅ built, on-contract |
| **Image pipeline** (relevance filter + glue) | You | `ClusterResult` + buckets + `ImageAnalysisResult` | now |
| **Name analysis** (Gemini) | You | `gemini` + `NameAnalysisResult` | now |
| **Mock data layer** (ports + `adapters/mock` + fixtures) | You | the ports + `MaterialRecord` | now |
| **Integration adapters** (R2, Directus) | You | the ports | parallel, anytime |

**The clean seam: front-end and back-end never touch each other's internals** —
they meet only at the `GET /search` → `SearchResponse` contract (§10). So your
partner builds the whole UI against a stubbed response while you build the
pipeline. Within the backend, the name and image lanes meet only at
`reconcile`/`run_batch`. Main risk to parallelism: churn in the §8 schema or the
§10 API shape — both locked, so agree changes before making them.

## 15. External systems & integration targets (reference)

All under `~/developer/acelab/`. You do **not** develop in these here.
- **Directus** — CMS / source of truth; later sink for color records. Admin:
  `https://acelab-directus-395321384746.us-east1.run.app/admin/content/company_colors`
- **The existing ingestion pipeline** — `product-scraping/` (and the vendored copy
  in `acelab-hatchet-workers/workers/ProductScraping/`). Classifies images as
  `ImageFileType.SWATCH` (`extraction/enums.py`) but never extracts the color —
  **this repo fills that gap.** The eventual inline hook drops our classify step
  into a post-persist stage on new `Swatch` rows.
- **R2** — Cloudflare object storage holding swatch images (referenced by key on
  persisted rows).
- **Reference implementations to read for patterns:**
  - `product-scraping/src/scraper/extraction/stages/extract.py` — the Gemini
    multimodal structured-output idiom (`response_json_schema`, strict JSON).
  - `product-scraping/src/scraper/classifier/engine.py` + `data/prompts/*.yaml` —
    a production classifier: strict-JSON prompts, config-driven, prompt caching,
    swappable pieces (and a prompt-management dashboard in `product-scraping/dashboard/`).

### Deferred / out of scope (later phases)
- Directus DB write-back (swap file sink for DB writer; schema already sink-agnostic).
- Inline pipeline hook on new `Swatch` rows.
- **Product-image fallback** for records with no swatch (riskiest — separating
  product color from background/lighting).
- Hex / color-picker / image-upload input modes.
- **Fine-grained "similar color" distance ranking** via stored `lab_centroids`
  (and, if ever wanted, embedding/semantic search) — explicitly *not* this phase.

## 16. Open questions (confirm before assuming)

- Is the **swatch name** readily queryable in the batch job's input, or only
  behind the deferred Directus DB? If names aren't available this phase, the name
  pre-check can't run and we're **image-first** — which changes the branch logic.
- The exact **source/format of the list of already-persisted records** to batch
  over (table / export / query), and how **R2 keys** are referenced on those rows.
- A few real swatches (name + image) to tune the §5 thresholds against, plus
  `GOOGLE_GENAI_API_KEY`.
- Whether a **neutral/beige** bucket is needed once tested on real materials.

## 17. Out of scope / do not use

- **`acelab-mcp`** is **unrelated** to this project — do not use it.
- `~/developer/acelab/hatchet-worker` (singular) is a Hatchet-quickstart scratch
  repo — ignore it.

## 18. Status

In active build. **Done:** the bucketing module (§5); shared value types with
`ClusterResult` unified into a single type (`core/models.py`); the config
bucketing section; the clustering adapters (k-means sweep + preprocess); the full
record + search-API schema (§8, §10); and a working demo `webapp/` (search +
admin + review queue + a live `/api/classify` that runs the real pipeline),
**aligned to the §10/§8 contract types** — `GET /search?color=` serves
`SearchResponse`, classify/review speak `ColorRecord`. **38 tests pass.**

**Next — You (backend):** `image_pipeline` glue + `name_analysis`, then the mock
data layer and `run_batch`. **Partner (UI):** `webapp/` is built; iterate on it.
**Team:** the §10-contract-vs-webapp-shapes drift decision (§16).

**Open external item:** a real `company_colors` sample for `fixtures/` (§16) —
needed before `run_batch` runs end-to-end on real data.

A discarded early spike (Gemini-vision color + embeddings) lives at
`acelab-hatchet-workers/experiments/color_classification/`; its name-analysis code
is salvageable, but its image-color approach is superseded by §7.
