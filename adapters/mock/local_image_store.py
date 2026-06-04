"""Mock ImageStore: reads swatch images from local files.

Implements `ports.image_store.ImageStore`. The record's image reference is a path
relative to a root dir (default `fixtures/images/`) — where the real adapter
would treat it as an R2 object key. Missing / unreadable file -> None (a normal
§6 branch, not an error).
"""

from __future__ import annotations

from pathlib import Path


class LocalImageStore:
    """`ImageStore` reading files under a root directory."""

    def __init__(self, root: str | Path = "fixtures/images") -> None:
        self._root = Path(root)

    def get_image(self, ref: str) -> bytes | None:
        if not ref:
            return None
        try:
            return (self._root / ref).read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError):
            return None
