"""Tests for the adapters/mock data layer round-trip (§12).

Must cover:
  - fixture_record_source: fixture JSON -> valid MaterialRecords; a
    malformed fixture fails loudly (fixtures are ours; bad one = bug)
  - local_image_store: existing file -> bytes; missing file -> None
    (a normal §6 branch, not an exception)
  - file_color_sink: records land in color_records.jsonl, needs_review
    records in review_queue.jsonl; lines round-trip back through the §8
    ColorRecord schema (what cli/search.py will read)
"""
