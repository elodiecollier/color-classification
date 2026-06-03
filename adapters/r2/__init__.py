"""STUB — real ImageStore over Cloudflare R2 (Phase 4 integration, §13).

Will implement ports/image_store.py: fetch swatch image bytes by the R2
object key carried on the persisted record. Do NOT build this phase —
the mock local_image_store covers development (§12). Blocked on §16:
how R2 keys are referenced on the rows we batch over.
"""
