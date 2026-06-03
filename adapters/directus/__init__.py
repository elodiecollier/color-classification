"""STUB — real Directus adapters (Phase 4 integration, §13).

Will implement, against the existing ports (core/ unchanged):
  - ports/record_source.py: query the already-persisted material/swatch
    rows from Directus.
  - ports/color_sink.py: write color records back to the DB (replaces the
    mock file sink; review queue likely becomes a status field).

Do NOT build this phase. Blocked on §13 step 11 (write-back ownership) and
the §16 open questions (record source format, name availability).
"""
