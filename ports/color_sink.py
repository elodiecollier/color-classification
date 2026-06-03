"""Port: where finished ColorRecords go (CLAUDE.md §8, §11, §12).

The §8 schema is deliberately sink-agnostic; this port is what makes the
sink swappable so the Directus writer can replace the file writer later
with NO pipeline changes (§4).

Will define:
  - ColorSink (interface):
      write(record: ColorRecord) -> None
      (+ flush/close semantics, e.g. context-manager support)

    Records with needs_review=True are routed to a separate review queue —
    whether that's a second file (mock) or a status field (Directus) is the
    adapter's business, not the caller's.

Implementations:
  - NOW:   adapters/mock — local JSONL file + a second review-queue file
           under output/
  - LATER: adapters/directus — DB write-back (deferred; ownership is an
           open item, §13 step 11)
"""
