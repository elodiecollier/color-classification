"""Tests (CLAUDE.md §13 Phase 3) — pytest; no network, no API keys.

Strategy: core/ is pure, so almost everything is testable with synthetic
colors and a mocked Gemini client. Only the clustering adapters need the
CV deps installed.
"""
