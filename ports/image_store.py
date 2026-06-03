"""Port: fetch swatch image bytes by reference (CLAUDE.md §11, §12).

The image pipeline (core/image_pipeline.py) takes raw bytes; THIS port is
where those bytes come from. The reference is whatever the record carries
(an R2 object key in production; a local file path in the mock).

Will define:
  - ImageStore (interface):
      get_image(ref) -> bytes | None
    Returning None (missing / unfetchable / undecodable image) is a normal
    outcome, not an exception — the per-record flow (§6) branches on it
    (falls back to name-only or the review queue).

Implementations:
  - NOW:   adapters/mock — local files under fixtures/images/
  - LATER: adapters/r2 — Cloudflare R2 object storage
"""
