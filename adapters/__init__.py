"""Concrete implementations of the `ports/` interfaces (CLAUDE.md §11, §12).

  mock/        NOW — fixture record source, local-file image store,
               JSONL file sink + review queue. The whole dev loop runs on
               these; we never touch Directus or the live pipeline.
  clustering/  NOW — the pluggable clustering strategies (K-means sweep,
               HDBSCAN). Lives here, not in core/, because of the heavy
               numpy/sklearn deps (core stays import-clean).
  r2/          LATER — real swatch-image fetch from Cloudflare R2. Stub.
  directus/    LATER — real record source + color write-back. Stub.

Integration = filling in r2/ + directus/ against the same port interfaces;
core/ and cli/ never change (§12).
"""
