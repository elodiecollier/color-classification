"""Accuracy harness: run the pipeline over LABELED swatches, report accuracy (§13).

    uv run python -m cli.eval                 # image-only (no API key)
    uv run python -m cli.eval --with-name     # name + image via reconcile (needs OPENROUTER_API_KEY)
    uv run python -m cli.eval --compare       # image-only vs +name side by side (needs key)
    uv run python -m cli.eval --labels path.json

Labels (`fixtures/eval_labels.json`): [{image, name?, expected: [bucket,...]}].
Reports, beyond a single % :
  - per-row expected vs. actual (✓/✗ on exact bucket-set match),
  - per-bucket RECALL (which colors we fail to detect — the tuning targets),
  - top CONFUSIONS (expected bucket → what we produced instead).
Built so jessi's real swatch data slots straight in: point `--labels` at a
labelled real set; the confusion/recall report scales to hundreds of rows.
A report, not a CI gate — always exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.models import ColorBucket


@dataclass(frozen=True)
class CaseResult:
    image: str
    expected: frozenset[ColorBucket]
    actual: frozenset[ColorBucket]

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


def to_buckets(names: list[str]) -> frozenset[ColorBucket]:
    """Validate label strings into buckets (a bad label is a loud bug, not noise)."""
    return frozenset(ColorBucket(n) for n in names)


def evaluate(
    cases: list[dict], classify: Callable[[dict], frozenset[ColorBucket]]
) -> list[CaseResult]:
    """Pure: run the injected `classify` over each case and pair with the label."""
    return [
        CaseResult(case["image"], to_buckets(case["expected"]), classify(case))
        for case in cases
    ]


def accuracy(results: list[CaseResult]) -> float:
    """Fraction of cases whose actual bucket-set exactly equals the expected set."""
    return sum(r.ok for r in results) / len(results) if results else 0.0


def per_bucket_recall(results: list[CaseResult]) -> dict[ColorBucket, tuple[int, int]]:
    """For each expected bucket: (hits, total) — how often we detected it when labelled."""
    hits: Counter[ColorBucket] = Counter()
    total: Counter[ColorBucket] = Counter()
    for r in results:
        for bucket in r.expected:
            total[bucket] += 1
            if bucket in r.actual:
                hits[bucket] += 1
    return {bucket: (hits[bucket], total[bucket]) for bucket in total}


def confusions(results: list[CaseResult]) -> Counter[tuple[ColorBucket, ColorBucket]]:
    """Count (missed-expected -> produced-instead) pairs across all cases.

    A case contributes (m, e) for every expected bucket m we failed to produce
    paired with every unexpected bucket e we produced — i.e. what each color got
    mistaken for. Misses with no substitute show up only in `per_bucket_recall`.
    """
    counts: Counter[tuple[ColorBucket, ColorBucket]] = Counter()
    for r in results:
        for missed in r.expected - r.actual:
            for got in r.actual - r.expected:
                counts[(missed, got)] += 1
    return counts


# --- CLI ---------------------------------------------------------------------
def main() -> None:
    args = _parse_args()
    warnings.filterwarnings("ignore")  # quiet sklearn's k-sweep ConvergenceWarnings

    cases = json.loads(Path(args.labels).read_text())
    store, strategy = _image_deps(args.images)

    if args.compare:
        llm = _require_llm()
        _report(evaluate(cases, _classify(store, strategy, None)), title="image-only", rows=False)
        print()
        _report(evaluate(cases, _classify(store, strategy, llm)), title="image + name", rows=False)
    else:
        llm = _require_llm() if args.with_name else None
        _report(evaluate(cases, _classify(store, strategy, llm)), title=None, rows=True)


def _report(results: list[CaseResult], *, title: str | None, rows: bool) -> None:
    if title:
        print(f"### {title}")
    if rows:
        print(f"{'image':<20}{'expected':<22}{'actual':<22}result")
        print("-" * 70)
        for r in results:
            print(f"{r.image:<20}{_fmt(r.expected):<22}{_fmt(r.actual):<22}"
                  f"{'OK' if r.ok else 'WRONG'}")
        print("-" * 70)

    correct = sum(r.ok for r in results)
    print(f"accuracy: {accuracy(results):.0%}  ({correct}/{len(results)})")

    recall = per_bucket_recall(results)
    misses = {b: (h, t) for b, (h, t) in recall.items() if h < t}
    if misses:
        print("per-bucket recall (misses first):")
        for bucket, (h, t) in sorted(misses.items(), key=lambda kv: kv[1][0] / kv[1][1]):
            print(f"  {bucket.value:<8} {h / t:>4.0%}  ({h}/{t})")

    conf = confusions(results)
    if conf:
        print("top confusions (expected → got instead):")
        for (missed, got), n in conf.most_common(10):
            print(f"  {missed.value} → {got.value}   ×{n}")


def _image_deps(images_root: str):
    from adapters.clustering.kmeans_sweep import KMeansSweep
    from adapters.mock.local_image_store import LocalImageStore
    from config.thresholds import DEFAULT

    store = LocalImageStore(images_root)
    strategy = KMeansSweep(
        k_max=DEFAULT.clustering.k_max,
        solid_delta_e=DEFAULT.clustering.solid_delta_e,
        silhouette_sample=DEFAULT.clustering.silhouette_sample,
        seed=DEFAULT.clustering.seed,
    )
    return store, strategy


def _require_llm():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: this mode requires OPENROUTER_API_KEY.", file=sys.stderr)
        sys.exit(1)
    from adapters.llm.openrouter import OpenRouterClient
    return OpenRouterClient(api_key=key)


def _classify(store, strategy, llm) -> Callable[[dict], frozenset[ColorBucket]]:
    """Build a classify(case) -> buckets. With `llm`, runs the full reconcile."""
    from adapters.clustering.preprocess import load_lab_pixels
    from config.thresholds import DEFAULT
    from core.image_pipeline import analyze_swatch

    def classify(case: dict) -> frozenset[ColorBucket]:
        img = store.get_image(case["image"])
        image_result = (
            analyze_swatch(img, load_pixels=load_lab_pixels, strategy=strategy, config=DEFAULT)
            if img is not None else None
        )
        if llm and case.get("name"):
            from core.models import MaterialRecord
            from core.name_analysis import analyze_name
            from core.reconcile import reconcile
            name_result = analyze_name(case["name"], llm)
            record = reconcile(
                MaterialRecord(material_id=case["image"], swatch_name=case.get("name")),
                name_result, image_result,
            )
            return frozenset(record.color_groups)
        return frozenset(image_result.buckets) if image_result else frozenset()

    return classify


def _fmt(buckets: frozenset[ColorBucket]) -> str:
    return ", ".join(sorted(b.value for b in buckets)) or "(none)"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Color classification accuracy harness")
    p.add_argument("--labels", default="fixtures/eval_labels.json", help="Labelled cases JSON")
    p.add_argument("--images", default="fixtures/images", help="Image root dir")
    p.add_argument("--with-name", action="store_true", help="Include the name signal (needs key)")
    p.add_argument("--compare", action="store_true",
                   help="Run image-only vs image+name side by side (needs key)")
    return p.parse_args()


if __name__ == "__main__":
    main()
