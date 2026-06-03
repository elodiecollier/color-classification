# color-classification

Enrich Acelab materials with **standard color classifications** — figure out the
real color(s) of each swatch (whose names are often non-intuitive, like
*"Fall River Glaze"*) — and demo searching them by color (type *"green"*, get
swatches that map to green like sage / lime / forest).

**Extraction** is the bulk of the work (Gemini for intuitive swatch *names*,
deterministic LAB/HSL clustering for swatch *images*). **Search** is a thin demo
over a fixed set of color buckets.

Built **standalone against a mocked data layer** first, to be integrated into
Acelab's Directus + ingestion pipeline once proven.

## Contributors / AI agents start here

📖 **Read [`CLAUDE.md`](./CLAUDE.md)** — the canonical context: the problem, the
division of labor (LLM for language, math for perceptual color), the color
buckets, the per-record flow, schema, build order, and open questions. It's
auto-loaded by Claude Code so every session shares the same context.

## Status

Planning complete (reconciled from two partners' plans). Next: scaffold + config
+ the bucketing module. See `CLAUDE.md` §13 for the step-by-step build order.
