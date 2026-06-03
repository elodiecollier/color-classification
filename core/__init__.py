"""Pure domain logic — NO external I/O (CLAUDE.md §11).

Rules for this package:
  - No network, no filesystem, no DB. All I/O is injected through the
    interfaces in `ports/`.
  - No heavy CV dependencies (numpy/sklearn live behind the clustering
    port's adapters); `core` must import cleanly with pydantic alone.
  - Every threshold comes from `config/` — nothing hard-coded.

Modules (one responsibility each):
  models.py          the §8 color record schema + shared value types
  buckets.py         HSL -> color bucket(s): achromatic-first, brown rule, hue bands
  image_pipeline.py  swatch image bytes -> LAB centroids -> bucket(s)
  name_analysis.py   swatch name -> bucket(s) + confidence, via Gemini
  gemini.py          thin Gemini client wrapper (strict-JSON structured output)
  reconcile.py       name vs image agreement -> confidence / conflict -> review
"""
