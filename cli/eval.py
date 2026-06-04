"""Accuracy harness: run the pipeline over LABELED swatches, report accuracy (§13 step 13).

    uv run python -m cli.eval                 # image-only (no API key)
    uv run python -m cli.eval --with-name     # name + image via reconcile (needs OPENROUTER_API_KEY)
    uv run python -m cli.eval --labels path.json

Labels (`fixtures/eval_labels.json`): [{image, name?, expected: [bucket,...]}].
Prints expected vs. actual per case (✓/✗ on exact bucket-set match) and an overall
accuracy %. A report, not a CI gate — always exits 0. Built so jessi's real
swatch data slots straight in: point `--labels` at a labelled real set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
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
    return sum(r.ok for r in results) / len(results) if results else 0.0


# --- CLI ---------------------------------------------------------------------
def main() -> None:
    args = _parse_args()
    warnings.filterwarnings("ignore")  # quiet sklearn's k-sweep ConvergenceWarnings

    cases = json.loads(Path(args.labels).read_text())
    classify = _build_classify(args)
    results = evaluate(cases, classify)

    print(f"{'image':<20}{'expected':<22}{'actual':<22}result")
    print("-" * 70)
    for r in results:
        print(
            f"{r.image:<20}{_fmt(r.expected):<22}{_fmt(r.actual):<22}"
            f"{'OK' if r.ok else 'WRONG'}"
        )
    acc = accuracy(results)
    print("-" * 70)
    print(f"accuracy: {acc:.0%}  ({sum(r.ok for r in results)}/{len(results)})")


def _build_classify(args: argparse.Namespace) -> Callable[[dict], frozenset[ColorBucket]]:
    from adapters.clustering.kmeans_sweep import KMeansSweep
    from adapters.clustering.preprocess import load_lab_pixels
    from adapters.mock.local_image_store import LocalImageStore
    from config.thresholds import DEFAULT
    from core.image_pipeline import analyze_swatch

    store = LocalImageStore(args.images)
    strategy = KMeansSweep(
        k_max=DEFAULT.clustering.k_max,
        solid_delta_e=DEFAULT.clustering.solid_delta_e,
        silhouette_sample=DEFAULT.clustering.silhouette_sample,
        seed=DEFAULT.clustering.seed,
    )

    llm = None
    if args.with_name:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("ERROR: --with-name requires OPENROUTER_API_KEY.", file=sys.stderr)
            sys.exit(1)
        from adapters.llm.openrouter import OpenRouterClient
        llm = OpenRouterClient(api_key=key)

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
    return p.parse_args()


if __name__ == "__main__":
    main()
