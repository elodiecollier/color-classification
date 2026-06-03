"""Tests for core/reconcile.py — the §6 decision table, exhaustively.

One test per row of the matrix:
  - agree (name ∩ image)            -> high confidence, source="reconciled"
  - CONFLICT (name blue, image grey)-> needs_review=True + conflict_reason
                                       set; image groups kept; NEVER a
                                       silent pick
  - image only / low-conf name      -> source="image", passes through
  - name only (no image)            -> source="name", confidence capped
  - neither signal                  -> review queue record
Plus: lab_centroids from the image result always survive onto the final
ColorRecord (§8 — required even now).
"""
