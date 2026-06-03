"""Swatch NAME -> bucket(s) + confidence, via Gemini (CLAUDE.md §6, §9).

The cheap pre-check, run only when a record has a name. Gemini handles
LANGUAGE only — "is this name intuitively a color?":
  - descriptive names resolve here ("Sage" -> green, high confidence)
  - non-intuitive names ("Fall River Glaze") return LOW confidence and the
    flow falls through to the image pipeline (which is authoritative anyway
    whenever an image exists).

Contract with the model (strict, defensive):
  - Prompt demands STRICT JSON: color_group(s) chosen ONLY from the fixed
    §5 taxonomy, plus confidence 0-1. Schema enforced via core/gemini.py
    structured output.
  - Parse failure or out-of-taxonomy output is NOT an error to retry into
    submission: treat as low confidence -> review queue (§9).

Will expose:
  - analyze_name(name, client, config) -> NameAnalysisResult

Salvage note: the discarded spike at
acelab-hatchet-workers/experiments/color_classification/ has working Gemini
name-analysis code to adapt (its image-color approach is superseded; ignore
that part). Prompt-style reference:
product-scraping/src/scraper/classifier/engine.py + data/prompts/*.yaml.
"""
