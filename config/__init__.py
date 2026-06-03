"""ALL tunable thresholds for the project, in ONE place (CLAUDE.md §5, §11).

Nothing else in the repo may hard-code a boundary or cutoff — every number
that could plausibly be re-tuned against real swatches lives in
`config/thresholds.py` and is imported from here. This is what makes
"run on real swatches, tune thresholds" (build step 8) a one-file change.
"""
