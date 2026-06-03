"""Image bytes -> downscaled (N, 3) CIELAB pixel array (CLAUDE.md §7 steps 1-2).

YOUR IMPLEMENTATION TASK (do this AFTER kmeans_sweep.py is green) — this is
the front half of the image pipeline: decode, downscale, convert to LAB.
Spec: the preprocess tests in tests/test_clustering.py.

Lives in adapters/ (not core/) because of the PIL + scikit-image deps.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, UnidentifiedImageError
from skimage.color import rgb2lab


def load_lab_pixels(image_bytes: bytes, max_edge: int = 200) -> np.ndarray | None:
    """Decode an image and return its pixels as an (N, 3) CIELAB float array.

    Returns None when the bytes aren't a decodable image — a NORMAL outcome
    per the §6 flow (record falls through to name-only / review), not an
    exception.
    """
    # 1-2. Decode + force RGB. (convert() drops any alpha channel — fine for
    # v1; transparent-background swatches are a watch-item to revisit.)
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        return None

    # 3. Downscale in place, keeping aspect ratio (thumbnail only shrinks).
    # Bounds clustering cost to ~max_edge² pixels.
    img.thumbnail((max_edge, max_edge))

    # 4. To LAB. rgb2lab expects floats in [0, 1], hence the /255.
    rgb = np.asarray(img, dtype=float) / 255.0
    lab = rgb2lab(rgb)

    # 5. Flatten (H, W, 3) -> (N, 3): clustering doesn't care about layout.
    return lab.reshape(-1, 3)
