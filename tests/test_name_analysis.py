"""Tests for core/name_analysis.py with a MOCKED Gemini client (no network).

Must cover (§9's defensive-parsing contract):
  - intuitive name ("Sage"): mock returns green/high -> resolves to green
  - non-intuitive name ("Fall River Glaze"): mock returns low confidence ->
    result signals fall-through to the image path
  - malformed JSON from the model -> low confidence, NOT an exception
  - out-of-taxonomy bucket from the model -> low confidence -> review,
    never persisted as-is
  - multiple buckets in the response are preserved as a list
"""
