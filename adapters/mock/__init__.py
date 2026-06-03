"""Mock data layer — the NOW adapters (CLAUDE.md §12).

Everything the batch runner needs to operate fully offline (except the one
Gemini name call):

  fixture_record_source.py  RecordSource over fixtures/*.json — records
                            mirroring the real persisted row shape
                            (ids, optional swatch name, image reference).
  local_image_store.py      ImageStore over local files in fixtures/images/
                            (the stand-in for R2; the record's image ref is
                            a relative path instead of an R2 key).
  file_color_sink.py        ColorSink writing two local files under output/:
                              - color records as JSONL (the §8 schema)
                              - a separate review-queue JSONL for
                                needs_review=True records.
                            cli/search.py reads the first file back.
"""
