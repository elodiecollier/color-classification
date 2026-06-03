# Color Classification

> Canonical context + plan for this repo. Auto-loaded by Claude Code. Read this
> first — it captures decisions and rationale that aren't recoverable from the
> code alone. Keep it updated as decisions change.

## 1. What this repo is

A **standalone** project to build and prove an end-to-end **color enrichment +
search** flow against a **mocked data layer**, then integrate it into Acelab's
existing systems (Directus, the Search API, and the `acelab-hatchet-workers`
Hatchet workers) once it works.

Building it standalone with mocks deliberately sidesteps two external blockers:
needing Directus access, and needing the (externally-owned) Search API extended.
We prove the logic here, then integrate.

## 2. The problem (why this exists)

- Acelab has **"company colors"**: a manufacturer's *proprietary* color name —
  e.g. Sun Mountain Door's **"Fall River Glaze"**. These live in **Directus**
  (collection `company_colors`).
- There is **no structured mapping** from a proprietary name to a standard color
  (nothing says "Fall River Glaze" ≈ a warm terracotta/brown). HSL data
  structures were built in Directus in anticipation but are **unpopulated**.
- Accurate color attributes exist only for the **easy subset** (e.g. a window
  offered in 5 colors). **Large color libraries / complex cases are unsolved.**
- Goal: let users **find colors by typing a description** ("warm terracotta
  matte").

**Key insight that shapes everything:** text search is only as good as the
*descriptive text* attached to each color. Proprietary marketing names carry
almost no color semantics, so embedding names alone gives poor recall for
descriptive queries. The real work is **enrichment** — normalizing a proprietary
color into standard, searchable attributes — which sits **upstream of search**.

## 3. The two layers

```
① ENRICH  company color (name [+ swatch image] [+ hex])
              │  agentic: classify → critic-check → parent-vet
              ▼
           standard color attributes  {family, descriptors[], HSL, hex, confidence}
              │  embed (text-descriptive)
              ▼
② SEARCH  vector + keyword index  ──▶ text query ("warm terracotta") returns colors
```

**Enrichment is the priority** — it's both the bottleneck and the unlock. Search
quality scales directly with enrichment coverage.

## 4. Key decisions (with rationale)

| Decision | Why |
|---|---|
| **v1 = text-descriptive embedding**, not perceptual LAB/ΔE color matching | Simpler, and matches Acelab's existing text-embedding search infra. Perceptual color is a different retrieval mechanism — deferred to a possible v2. |
| **Enrichment-first** | Proprietary names aren't descriptive; without enrichment, search is just brand/keyword lookup. |
| **Standalone repo + mocked DB now; integrate later** | Unblocks development without Directus access or Search-API changes. |
| **Build against ports/interfaces, not the mock directly** | Makes "integrate later" a matter of swapping adapters; the domain core never changes. |
| **Gemini for the classifier** | Multimodal, cheap `flash` tier, and it matches Acelab's existing extraction idiom (`response_json_schema` structured output). |
| **Embeddings = OpenAI `text-embedding-3-small` via OpenRouter, 1536-dim** | **Required** so vectors are compatible with Acelab's existing `search_api` pgvector HNSW indexes at integration time. |

## 5. Architecture / intended repo layout

```
color-classification/
  core/                  # pure domain — NO external I/O
    models.py            # ColorInput · ColorClassification · CheckResult · VettedColor
    gemini.py            # Gemini client + structured-output helper + image loading
    stages.py            # classify (generator) · check (critic)
    pipeline.py          # classify → check → vet  (parent orchestrator + bounded retry)
  ports/                 # the integration seam — interfaces only
    color_repository.py  # read company colors · write enriched attributes
    search_index.py      # index enriched colors · text-query them
  adapters/
    mock/                # NOW   — in-memory / SQLite / JSON fixtures
    directus/            # LATER — real Directus           (stub for now)
    search_api/          # LATER — real Acelab Search API  (stub for now)
  fixtures/
    company_colors.json  # stand-in for Directus company_colors (name, company, image_url, hex)
  cli/run.py             # end-to-end: load colors → classify → store → (optional) search
  tests/
```

The mock models exactly the two Directus surfaces we depend on: the
`company_colors` read *in*, and the enriched attributes (HSL structures) written
*out*. Keep `core/` free of external dependencies; all I/O goes through `ports/`.

### Mocking the database (concrete)

We never touch Directus or the Search API during development. Instead:

- **Input — `company_colors`**: `fixtures/company_colors.json`, an array of
  records mirroring the real Directus collection's fields (e.g. `id, name,
  company, image_url, hex, finish, material, …` — to be confirmed from a real
  export). Read via `adapters/mock/MockColorRepository` (implements the
  `ColorRepository` port).
- **Output — enriched attributes (the HSL structures)**:
  `MockColorRepository.save_enrichment(id, attrs)` writes to a local file
  (`out/enriched.json`) or SQLite — standing in for writing back to Directus.
- **Search index (Search API + pgvector)**: `adapters/mock/MockSearchIndex`
  holds `(id, embedding, attrs)` in memory (or SQLite) and answers `query(text)`
  by embedding the query and computing cosine similarity in Python. Vectors are
  **1536-dim** to match real `search_api` at integration time.
- **Embeddings**: a pluggable `Embedder` port — `OpenRouterEmbedder` (real
  `text-embedding-3-small`) or `FakeEmbedder` (deterministic, offline, zero keys).

Because each sits behind a port, **integration = writing `adapters/directus/*`
and `adapters/search_api/*` against the same interfaces, with `core/` unchanged.**

## 6. The classifier (core) design

Agentic, multi-stage — matching the pattern the team uses elsewhere:

- **Tiered input signal**: swatch image (vision) > hex > name-only. The output
  records `signal_source` and an honest `confidence` reflecting which was used.
- **`classify` (generator)** → produces `ColorClassification` via Gemini
  structured output.
- **`check` (critic)** → a second Gemini call verifies the candidate against the
  source; can flag issues and **suggest a corrected family** (not just reject).
- **`pipeline` (parent vet)** → accept when the critic approves and confidence
  isn't low; otherwise re-classify with the critic's feedback (bounded retries);
  else return `needs_review`. Low-confidence/complex cases go to review rather
  than being silently published.
- pydantic models double as the **future Hatchet task input/output validators**,
  so the port is mechanical.

**Gemini specifics that matter** (learned from the existing codebase):
- Structured output via `GenerateContentConfig(response_mime_type="application/json",
  response_json_schema=Model.model_json_schema())`, then `Model.model_validate_json(response.text)`.
- Set **`max_output_tokens`** generously (~2000): `gemini-2.5+`/`3` models burn
  output tokens on internal thinking and will otherwise truncate the JSON.
- Image parts via `types.Part.from_bytes(data=..., mime_type=...)`.

## 7. Integration plan (the "later" — do not build yet)

Three mechanical swaps, `core/` untouched:
1. **`mock` ColorRepository → `directus` adapter** — read `company_colors`, write
   enriched attributes back to the Directus HSL structures.
2. **`mock` SearchIndex → Acelab Search API** — this is the "**register colors**"
   step: teach the Search API a new *colors* searchable object — a
   `search_api.colors_search` table + a `SearchConfig` (which columns to embed,
   the vector + `tsvector` columns) + a `/api/v1/colors/search` route. **Note:**
   that service's source is **not** in `acelab-hatchet-workers` (only the backfill
   half + shared config types are); locating/owning that change is an open item.
3. **`cli` orchestrator → Hatchet workflow** in `acelab-hatchet-workers`:
   `classify`/`check` become `@workflow.task`s, `pipeline` becomes the workflow.

## 8. External systems (reference — you do NOT develop in these here)

- **Directus** — headless CMS; source of truth for `company_colors` and the HSL
  structures. Admin: `https://acelab-directus-395321384746.us-east1.run.app/admin/content/company_colors`
- **Acelab Search API** — deployed FastAPI service, `/api/v1/*`, Postgres +
  pgvector (HNSW cosine). Consumed via the `acelab` Python SDK. Documented in
  `~/developer/acelab/docs/search-api/` (OpenAPI + SDK). Its query source is not
  in any local repo.
- **`search_api` Postgres schema** — the `*_search` tables: `embedding vector(1536)`
  + `search_vector tsvector` + `*_embedded_hash`; incremental re-embed via
  `content_hash IS DISTINCT FROM embedded_hash` (the "VEC-43" pattern).
- **Cloudflare R2** — where the scraping pipeline stores swatch images.

## 9. Reference implementations in sibling repos (read for patterns)

All under `~/developer/acelab/`:
- `acelab-hatchet-workers/workers/IntroductionProxyService/src/introduction_proxy/moderation.py`
  — LLM classifier via a forced tool-call (email moderation). The original
  "classify with structured output" reference.
- `acelab-hatchet-workers/workers/VectorSearch/` — the search **backfill** worker
  and the `SearchConfig` registry (`search/types.py`). `backfill_material_embeddings.py`
  is the template for the eventual color backfill; `backfill_search_shared.py` has
  reusable helpers.
- `product-scraping/src/scraper/classifier/engine.py` + `data/prompts/stage1.yaml`,
  `stage2.yaml` — a **production two-stage classifier**. Lessons to adopt at port
  time: provider-agnostic client (Anthropic ↔ Gemini), prompt **caching** (matters
  if we ever feed a large standard-color reference), coarse→refine with a
  **REROUTE** escape hatch, and **YAML/DB-backed versioned prompts** (edited via a
  Next.js prompt dashboard in `product-scraping/dashboard/`).
- `product-scraping/src/scraper/extraction/stages/extract.py` — the Gemini
  multimodal structured-extraction idiom. **Note:** that pipeline already labels
  images as `ImageFileType.SWATCH` (`extraction/enums.py`) but never extracts the
  color — **this repo fills exactly that gap.**

## 10. Conventions

- Python 3.13, pydantic. Type hints throughout.
- Field `description=`s on pydantic schemas double as per-field instructions to
  the LLM (mirrors `extraction/models.py`).
- `Confidence = Literal["high", "medium", "low"]`.
- Strip LLM sentinel values ("unknown", "n/a", "", …) before persisting.
- `core/` stays free of external deps; all I/O behind `ports/`.

## 11. Open questions

- **Sample data**: need real `name [+ swatch image]` examples to validate against
  (Directus access, or a hand-built fixture).
- **Search API ownership**: who extends the Search API to add a colors object type.
- **Write-back target**: do enriched attributes go back into Directus HSL
  structures, or a new store?
- **Mock embeddings**: real `text-embedding-3-small` via OpenRouter (realistic,
  small cost) vs a fake offline embedder (zero keys).
- **Available signals**: what's actually present per company color (images? hex?
  finish/material?).

## 12. Out of scope / do not use

- **`acelab-mcp`** is **unrelated** to this project — do not use it.
- `~/developer/acelab/hatchet-worker` (singular) is a Hatchet-quickstart scratch
  repo — ignore it.
- Perceptual LAB color matching — deferred to a possible v2.

## 13. Implementation walkthrough (step by step)

**Status:** planning. A classifier spike exists at
`acelab-hatchet-workers/experiments/color_classification/` and will be **moved
into `core/`** here. No code in this repo yet.

Ownership tags: **[You]** = human contributor, **[Claude]** = agent.

### Phase 0 — Ground & scaffold
1. **[You] Pull grounding inputs from Directus.** Export ~10–30 representative
   `company_colors` rows (or list the field names + paste a few examples).
   Confirm which signals exist per row: a **swatch image URL**? a **hex**? a
   company name? finish/material/description? Make `GOOGLE_GENAI_API_KEY`
   available (and `OPENROUTER_API_KEY` if we use real embeddings).
   *This grounds the mock schema in reality and lets the classifier actually run.*
2. **[Claude] Scaffold the repo** — `pyproject.toml` + skeleton (`core/`,
   `ports/`, `adapters/mock/`, `fixtures/`, `cli/`, `tests/`); move the spike
   into `core/`.
3. **[Claude] Define the ports** — `ColorRepository`, `SearchIndex`, `Embedder`.
4. **[Claude] Build the mock** — `fixtures/company_colors.json` from your sample
   + `MockColorRepository` over it.

### Phase 1 — Classifier on mock data
5. **[Claude] Wire `cli/run.py`** — load colors via the repo → run
   `classify → check → vet` → write enriched attrs back via the repo.
6. **[You + Claude] Run it** on the fixture with your key; review outputs together.
7. **[Claude] Tune** prompts/schema from results; verify confidence gating routes
   hard/low-confidence cases to `needs_review`.

### Phase 2 — Search half (optional first cut)
8. **[Claude]** Add `Embedder` (OpenRouter real or fake) + `MockSearchIndex`;
   index the enriched colors.
9. **[Claude]** Add a `cli` search command: text query → top-N colors.
10. **[You + Claude]** Sanity-check descriptive queries ("warm terracotta")
    against the enriched set.

### Phase 3 — Tests & eval
11. **[Claude]** Unit tests (mocked LLM) for stages/pipeline/adapters; a small
    accuracy eval on the simple-product subset where ground truth exists.

### Phase 4 — Integration (blocked on §11 open questions)
12. **[You]** Resolve ownership: Directus write-back target; who extends the
    Search API for a colors object; production keys/secrets.
13. **[Claude]** Implement `adapters/directus/*` + `adapters/search_api/*`
    against the same ports; port `core` orchestration to a Hatchet workflow in
    `acelab-hatchet-workers`.

## 14. Parallel workstreams (who can work on what)

The ports/adapters design exists precisely so multiple people work at once.
**One prerequisite: lock the contracts first** — the three port signatures
(`ColorRepository`, `SearchIndex`, `Embedder`) and the `ColorClassification`
output schema. They're small; agree them in one sitting. After that, these run
in parallel:

| Stream | Scope | Depends only on | Can start |
|---|---|---|---|
| **A. Classifier core** | `classify → check → vet`, prompts, Gemini | core models | after contracts |
| **B. Mock data layer** | fixtures, `MockColorRepository`, store | `ColorRepository` port | after contracts (fabricated fixture if no real export yet) |
| **C. Search half** | `Embedder`, `MockSearchIndex`, query | `SearchIndex` port + `ColorClassification` schema | after contracts (use synthetic enriched records) |
| **D. Eval / tests** | accuracy harness, unit tests w/ mocked LLM | models + ports | after contracts |
| **E. Directus adapter** (integration) | real read/write | `ColorRepository` port + Directus access | parallel, anytime |
| **F. Search API colors object** (integration) | register colors object + adapter | external Search API codebase | parallel, separate owner/repo |

**Critical path:** contracts → (A, B, C, D in parallel) → integrate (E, F).
The classifier (A) and search (C) only ever meet through the
`ColorClassification` schema and the `SearchIndex` port — neither needs the
other's internals. **Main risk to parallelism is schema churn:** if
`ColorClassification` changes, C/D/E shift — so stabilize it early.
