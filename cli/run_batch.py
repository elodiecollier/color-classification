"""Batch runner: classify every record end-to-end and write results (CLAUDE.md §13 step 10).

Usage:
    uv run python -m cli.run_batch                      # image-only (no API key needed)
    uv run python -m cli.run_batch --with-name          # name + image (needs OPENROUTER_API_KEY)
    uv run python -m cli.run_batch --limit 2            # first 2 records, for quick iteration
    uv run python -m cli.run_batch --fixtures path.json --output out/

Outputs (under output/ by default):
    color_records.jsonl   — published records (§8 schema)
    review_queue.jsonl    — needs_review=True records, for human triage

Per-record flow (CLAUDE.md §6 three-way branch):
    Has image ref  -> analyze_swatch (authoritative)
    Has name       -> analyze_name if --with-name (cheap pre-check / corroboration)
    reconcile(record, name_result, image_result) -> ColorRecord -> sink
    One bad record is flagged and skipped; the batch never aborts.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

from adapters.clustering.kmeans_sweep import KMeansSweep
from adapters.clustering.preprocess import load_lab_pixels
from adapters.mock.file_color_sink import FileColorSink
from adapters.mock.fixture_record_source import FixtureRecordSource
from adapters.mock.local_image_store import LocalImageStore
from config.thresholds import DEFAULT
from core.image_pipeline import analyze_swatch
from core.models import ColorRecord, MaterialRecord
from core.name_analysis import analyze_name
from core.reconcile import reconcile


def main() -> None:
    args = _parse_args()

    llm_client = None
    if args.with_name:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("ERROR: --with-name requires OPENROUTER_API_KEY to be set.", file=sys.stderr)
            sys.exit(1)
        from adapters.llm.openrouter import OpenRouterClient
        llm_client = OpenRouterClient(api_key=key)

    source = FixtureRecordSource(args.fixtures)
    image_store = LocalImageStore()
    strategy = KMeansSweep(
        k_max=DEFAULT.clustering.k_max,
        solid_delta_e=DEFAULT.clustering.solid_delta_e,
        silhouette_sample=DEFAULT.clustering.silhouette_sample,
        seed=DEFAULT.clustering.seed,
    )

    records = list(source.iter_records())
    if args.limit:
        records = records[: args.limit]

    print(f"Processing {len(records)} record(s) "
          f"({'name + image' if llm_client else 'image-only'}) …\n")

    published = skipped = 0
    with FileColorSink(args.output) as sink:
        for record in records:
            result = _classify_one(record, llm_client, image_store, strategy, args)
            if result is None:
                skipped += 1
                continue
            sink.write(result)
            published += 1
            _print_result(record, result)

    print(f"\nDone. {published} written ({skipped} skipped).")
    print(f"  Published  → {args.output}/color_records.jsonl")
    print(f"  Review     → {args.output}/review_queue.jsonl")


def _classify_one(
    record: MaterialRecord,
    llm_client,
    image_store: LocalImageStore,
    strategy: KMeansSweep,
    args: argparse.Namespace,
) -> ColorRecord | None:
    """Classify one record; return None (and print a warning) if it errors."""
    try:
        # --- name signal (cheap, optional) ---
        name_result = None
        if llm_client and record.swatch_name:
            name_result = analyze_name(
                record.swatch_name, llm_client, company=record.company
            )

        # --- image signal (authoritative when present) ---
        image_result = None
        if record.image_ref:
            image_bytes = image_store.get_image(record.image_ref)
            if image_bytes is not None:
                image_result = analyze_swatch(
                    image_bytes,
                    load_pixels=load_lab_pixels,
                    strategy=strategy,
                    config=DEFAULT,
                )

        return reconcile(record, name_result, image_result)

    except Exception:
        print(f"  [SKIP] {record.material_id} — unexpected error:")
        traceback.print_exc(limit=3)
        return None


def _print_result(record: MaterialRecord, result: ColorRecord) -> None:
    name = record.swatch_name or record.material_id
    groups = ", ".join(str(b) for b in result.color_groups) or "(none)"
    conf = f"{result.confidence:.0%}"
    flag = " ⚠ REVIEW" if result.needs_review else ""
    reason = f"\n    conflict: {result.conflict_reason}" if result.conflict_reason else ""
    print(f"  {name:<28} [{result.source:<12}]  {groups}  ({conf}){flag}{reason}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Color classification batch runner")
    p.add_argument("--fixtures", default="fixtures/records.json", help="Input fixture JSON")
    p.add_argument("--output", default="output", help="Output directory for JSONL files")
    p.add_argument("--with-name", action="store_true",
                   help="Enable name pre-check via Gemini (needs OPENROUTER_API_KEY)")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Process only the first N records (for quick iteration)")
    return p.parse_args()


if __name__ == "__main__":
    main()
