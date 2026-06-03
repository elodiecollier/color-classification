"""HSL -> color bucket mapping — the spine of the project (CLAUDE.md §5, §14).

Pure function(s) from an HSL value to one ColorBucket, driven entirely by
`config/thresholds.py`. Testable in isolation against synthetic colors —
this is build step 3, done before anything that depends on it.

Decision order (the order IS the algorithm — see §5):
  1. ACHROMATIC FIRST: very low saturation, or lightness near 0/100
     -> black / white / grey, regardless of hue. (This is what catches
     each checkerboard tile before hue logic can mislabel it.)
  2. BROWN: not a pure hue — roughly orange/red hue + low lightness +
     low/moderate saturation. Must be checked BEFORE the hue bands, or
     browns leak into orange/red.
  3. HUE BANDS: red, orange, yellow, green, blue, purple.
     Cyan folds into blue/green; pink folds into red (boundary choices
     encoded in config, not here).
  4. Optional light/dark sub-tier, only when enabled in config.

Will expose:
  - bucket_for_hsl(hsl, config) -> ColorBucket        (single color)
  - buckets_for_centroids(centroids, config) -> list  (dedup'd, ordered by
    coverage — used by the image pipeline; a multi-tone swatch yields
    multiple buckets)
"""
