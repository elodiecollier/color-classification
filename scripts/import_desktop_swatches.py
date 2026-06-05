"""One-off importer: pull a folder of swatch images into the fixtures DB.

Copies every image from a source folder into fixtures/images/ and appends a
MaterialRecord per image to fixtures/records.json (swatch_name = file stem).
Idempotent on swatch_name: re-running skips names already present.

Usage:
    uv run python -m scripts.import_desktop_swatches "~/Desktop/Swatches"
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
COMPANY = "Acelab Samples"

FIXTURES_JSON = Path("fixtures/records.json")
IMAGES_DIR = Path("fixtures/images")


def slug(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in name]
    s = "".join(keep)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-") or "swatch"


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Desktop/Swatches").expanduser()
    if not src.is_dir():
        raise SystemExit(f"not a folder: {src}")

    records = json.loads(FIXTURES_JSON.read_text())
    existing_names = {r.get("swatch_name") for r in records}
    used_material_ids = {r["material_id"] for r in records}
    next_swatch_n = (
        max(
            (int(r["swatch_id"][1:]) for r in records
             if isinstance(r.get("swatch_id"), str) and r["swatch_id"][1:].isdigit()),
            default=0,
        )
        + 1
    )

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    images = sorted(p for p in src.iterdir() if p.suffix.lower() in IMAGE_EXTS)

    added = 0
    skipped = []
    for img in images:
        name = img.stem
        if name in existing_names:
            skipped.append(f"{name} (name already in DB)")
            continue

        dest = IMAGES_DIR / img.name
        shutil.copy2(img, dest)

        material_id = slug(name)
        base = material_id
        i = 2
        while material_id in used_material_ids:
            material_id = f"{base}-{i}"
            i += 1
        used_material_ids.add(material_id)

        records.append({
            "material_id": material_id,
            "swatch_id": f"s{next_swatch_n}",
            "swatch_name": name,
            "company": COMPANY,
            "image_ref": img.name,
        })
        existing_names.add(name)
        next_swatch_n += 1
        added += 1

    FIXTURES_JSON.write_text(json.dumps(records, indent=2) + "\n")
    print(f"Added {added} swatch(es); skipped {len(skipped)}.")
    for s in skipped:
        print(f"  skip: {s}")
    print(f"Total records now: {len(records)}")


if __name__ == "__main__":
    main()
