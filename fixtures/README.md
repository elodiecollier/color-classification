# fixtures/ — the mocked data layer's data (CLAUDE.md §12)

Stand-ins for the real persisted rows + R2 images, so development never
touches Directus or the live pipeline.

## Contents (to be added)

- `records.json` — the records to batch over, mirroring the **real persisted
  row shape**: ids, optional swatch `name`, optional image reference (the
  field that carries an R2 key in production; here, a path relative to
  `fixtures/images/`). Must parse as `core.models.MaterialRecord`. Include
  all three §6 branches: image+name, name-only, neither — and at least one
  deliberate name/image conflict to exercise the review queue.
- `images/` — small local swatch images read by the mock image store.
  Curated hard cases for tuning §7: solid color, black/white **checkerboard**
  (must classify black + white, never grey), gradient, multi-tone, and a few
  beige/tan/cream neutrals (the §5 watch-item).

## Pending real data (§16)

Real `name + image` swatch examples are an open input from the team — needed
to tune `config/thresholds.py`. Until then, fixtures are synthetic/hand-built.
The exact real row format is also unconfirmed; update `records.json` (and
`core/models.py` field names) once known.
