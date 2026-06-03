"""Search demo: color term -> bucket -> matching records (CLAUDE.md §10).

Deliberately thin — exists to DEMONSTRATE the extraction, not as production
search. No embeddings, no external Search API, no UI (§4).

Flow:
  1. Map the user's term to a ColorBucket:
       - exact bucket name ("green") -> direct hit, no LLM call
       - other terms ("sage", "forest") -> reuse core/name_analysis
  2. Scan output/color_records.jsonl for records whose color_groups
     include that bucket.
  3. Print matches (id, name, groups, confidence; flag needs_review ones).

This is the acceptance demo: search "green" returns the sage / lime /
forest swatches (§2).
"""
