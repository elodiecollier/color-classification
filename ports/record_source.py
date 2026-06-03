"""Port: where the records to classify come from (CLAUDE.md §11, §12).

Yields MaterialRecord instances (core/models.py) — ids, optional swatch
name, optional swatch image reference — mirroring the real persisted row
shape so the fixture and the eventual real source are interchangeable.

Will define:
  - RecordSource (interface):
      iter_records() -> Iterable[MaterialRecord]

Implementations:
  - NOW:   adapters/mock — reads fixtures/*.json
  - LATER: adapters/directus — queries the real persisted rows

OPEN QUESTION (§16) that shapes this interface: the exact source/format of
the record list (table / export / query), whether the swatch NAME is even
queryable this phase, and how R2 keys are referenced. If names turn out to
be unavailable, the optional-name field stays None and the flow becomes
image-first — the interface itself shouldn't need to change.
"""
