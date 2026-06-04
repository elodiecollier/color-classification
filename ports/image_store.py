"""Port: fetch swatch image bytes by reference (CLAUDE.md §11, §12).

`core/image_pipeline.py` takes raw bytes; THIS is where they come from. The
reference is whatever the record carries — an R2 object key in production, a
local path in the mock. Returning None (missing / unfetchable) is a NORMAL §6
outcome (fall through to name-only / review), not an exception.
"""

from __future__ import annotations

from typing import Protocol


class ImageStore(Protocol):
    """Fetches swatch image bytes by reference."""

    def get_image(self, ref: str) -> bytes | None:
        """Return the image bytes for `ref`, or None if absent/unfetchable."""
        ...
