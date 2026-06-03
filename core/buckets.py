"""HSL -> color bucket mapping — the spine of the project (CLAUDE.md §5, §14).

Pure functions from a color to one `ColorBucket`, driven entirely by
`config/thresholds.py`. No external/CV dependencies (LAB->HSL conversion is
done here in pure Python) so this stays testable in isolation.

Decision order (the order IS the algorithm — see §5):
  1. ACHROMATIC FIRST: lightness near 0/100 -> black/white regardless of hue;
     very low saturation -> grey. (Catches each checkerboard tile before hue
     logic can mislabel it.)
  2. BROWN: orange-hued + low lightness. Checked BEFORE the hue bands, or
     browns leak into orange/red.
  3. HUE BANDS: red, orange, yellow, green, blue, purple.

Exposes:
  - bucket_for_hsl(hsl, config)        -> ColorBucket           (single color)
  - buckets_for_centroids(centroids, config) -> list[ColorBucket]
        (dedup'd, ordered by total coverage desc; multi-tone swatch -> many)
  - lab_to_hsl(lab) -> HSL             (helper, also reused by the pipeline)
"""

from __future__ import annotations

from collections.abc import Iterable

from config.thresholds import DEFAULT, BucketingThresholds
from core.models import ClusterResult, ColorBucket, HSL, LabColor


def bucket_for_hsl(hsl: HSL, config: BucketingThresholds = DEFAULT.bucketing) -> ColorBucket:
    """Map one HSL color to its bucket. Pure; deterministic; config-driven."""
    h, s, l = hsl.h % 360.0, hsl.s, hsl.l

    # 1. Achromatic first.
    if l <= config.black_max_lightness:
        return ColorBucket.BLACK
    if l >= config.white_min_lightness:
        return ColorBucket.WHITE
    if s <= config.achromatic_max_saturation:
        return ColorBucket.GREY

    # 2. Brown (dark, orange-hued) before the hue bands.
    if config.brown_hue_min <= h <= config.brown_hue_max and l <= config.brown_max_lightness:
        return ColorBucket.BROWN

    # 3. Hue bands.
    for bucket, lo, hi in config.hue_bands:
        if lo <= hi:
            if lo <= h < hi:
                return bucket
        else:  # wrap-around band (red)
            if h >= lo or h < hi:
                return bucket

    return ColorBucket.RED  # unreachable if bands tile [0, 360)


def buckets_for_centroids(
    centroids: Iterable[ClusterResult],
    config: BucketingThresholds = DEFAULT.bucketing,
) -> list[ColorBucket]:
    """Map clustered swatch centroids to buckets.

    Aggregates coverage per bucket (two clusters that both read 'blue' merge into
    one 'blue'), then returns the distinct buckets ordered by total coverage
    descending, ties broken by first appearance. A multi-tone swatch yields
    multiple buckets — a black/white checkerboard yields [black, white].
    """
    coverage: dict[ColorBucket, float] = {}
    first_seen: list[ColorBucket] = []
    for cluster in centroids:
        bucket = bucket_for_hsl(lab_to_hsl(cluster.centroid), config)
        if bucket not in coverage:
            coverage[bucket] = 0.0
            first_seen.append(bucket)
        coverage[bucket] += cluster.coverage
    return sorted(coverage, key=lambda b: (-coverage[b], first_seen.index(b)))


# --- color-space conversion (pure Python, no numpy) -------------------------

# D65 reference white, and CIE standard constants.
_XN, _YN, _ZN = 0.95047, 1.0, 1.08883
_EPS = 216 / 24389  # 0.008856
_KAPPA = 24389 / 27  # 903.3


def lab_to_hsl(lab: LabColor) -> HSL:
    """CIELAB (D65) -> HSL. Goes via XYZ -> linear sRGB -> sRGB -> HSL."""
    r, g, b = _lab_to_srgb(lab.L, lab.a, lab.b)
    h, s, light = _srgb_to_hsl(r, g, b)
    return HSL(h=h, s=s, l=light)


def _lab_to_srgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    xr = fx**3 if fx**3 > _EPS else (116 * fx - 16) / _KAPPA
    yr = fy**3 if L > _KAPPA * _EPS else L / _KAPPA
    zr = fz**3 if fz**3 > _EPS else (116 * fz - 16) / _KAPPA

    x, y, z = xr * _XN, yr * _YN, zr * _ZN

    # XYZ -> linear sRGB (D65).
    rl = x * 3.2406 + y * -1.5372 + z * -0.4986
    gl = x * -0.9689 + y * 1.8758 + z * 0.0415
    bl = x * 0.0557 + y * -0.2040 + z * 1.0570

    return tuple(_gamma(c) for c in (rl, gl, bl))  # type: ignore[return-value]


def _gamma(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    return 1.055 * c ** (1 / 2.4) - 0.055 if c > 0.0031308 else 12.92 * c


def _srgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    mx, mn = max(r, g, b), min(r, g, b)
    light = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, light  # achromatic
    d = mx - mn
    s = d / (2 - mx - mn) if light > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return (h * 60) % 360, s, light
