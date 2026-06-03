"""Mock ColorSink: appends ColorRecords to local JSONL files under output/.

Implements ports/color_sink.py. Two output files:
  - output/color_records.jsonl  — every finished record (§8 schema, one
    JSON object per line); this is what cli/search.py queries.
  - output/review_queue.jsonl   — records with needs_review=True (conflicts,
    low confidence, no-signal records), for human triage.

JSONL over CSV: records contain nested lists (lab_centroids, color_groups)
that don't flatten cleanly. The Directus writer replaces this class later
with no caller changes (§4).
"""
