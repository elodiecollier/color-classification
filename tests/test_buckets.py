"""Tests for core/buckets.py against synthetic HSL values (§13 step 3).

The spine module — these tests gate everything downstream. Must cover:
  - one obvious in-band color per chromatic bucket (red..purple)
  - ACHROMATIC-FIRST: low saturation -> grey regardless of hue;
    lightness ~0 -> black; ~100 -> white
  - BROWN rule: dark low-sat orange/red -> brown, NOT orange/red;
    and a bright saturated orange stays orange (rule doesn't overreach)
  - boundary folds: cyan-ish -> blue/green, pink-ish -> red (per config)
  - hue-band edge values land deterministically on one side
  - light/dark sub-tier only activates when the config flag is on
  - buckets_for_centroids: multi-centroid input -> multiple buckets,
    dedup'd, ordered by coverage
"""
