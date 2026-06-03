"""Batch runner: classify every persisted record end-to-end (CLAUDE.md §6, §13 step 7).

The composition root — wires the mock adapters into the ports and drives
the per-record flow. Per record, the 3-way branch (§6):

  1. HAS SWATCH IMAGE -> image pipeline is AUTHORITATIVE
       - name pre-check first if a name exists (cheap corroboration)
       - fetch bytes via image_store -> core/image_pipeline
       - core/reconcile merges the two signals; conflicts -> review queue
  2. NAME ONLY (no usable image) -> core/name_analysis alone;
       low confidence -> review queue
  3. NEITHER -> straight to review queue
       (product-image fallback is a deferred stretch goal, §15)

Every outcome is written through the color sink: finished records to the
JSONL output, needs_review records to the review-queue file. The runner
must be resilient per-record — one bad image or one failed Gemini call
skips/flags THAT record, never aborts the batch.

Planned flags: fixture path, output dir, clustering strategy selection
(kmeans | hdbscan, for the A/B), limit-N for cheap iteration while tuning
config/thresholds.py against real swatches (§13 step 8).
"""
