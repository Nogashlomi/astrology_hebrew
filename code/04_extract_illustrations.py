#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP 4 - Extract illustrations (diagrams, tables, decorations, initials) from the manuscript pages.

Detection uses CorDeep (YOLOv5 trained on printed Sphaera editions, MPIWG), cloned read-only into
external/sphaera-cordeep/ and run in its own Python environment through uv (see README).
CorDeep was trained on printed books, not manuscripts; expect more misses and false positives here.
CorDeep's classes: Content Illustration, Decoration, Initial, Printer's Mark, Table.

Input:  data/manuscripts/<manuscript folder>/NNNN.jpg (+ metadata.json)
Output: data/illustrations/<manuscript folder>/<page>_<class>_NN.jpg   one crop per detection
        data/illustrations/illustrations.csv                           one row per crop, columns ILLUSTRATION_COLUMNS

Known false positives: blank pages and covers (removed by --max-area), microfilm target cards
("START/END", resolution charts) and photographers' rulers (kept; remove them by hand or by score).

Usage:  python code/04_extract_illustrations.py [--only <folder name>] [--conf 0.25] [--overwrite]
"""
import argparse
import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from PIL import Image

from paths import PROJECT_ROOT, MANUSCRIPTS_DIR, ILLUSTRATIONS_DIR

CORDEEP_DIR = PROJECT_ROOT / "external" / "sphaera-cordeep"
CORDEEP_CLASSES = ["Content Illustration", "Decoration", "Initial", "Printer's Mark", "Table"]
METHOD = "cordeep-yolov5_300epochs_aug"
DUPLICATE_OVERLAP = 0.6   # two boxes on one page overlapping this much (IoU) are one drawing

ILLUSTRATIONS_CSV = ILLUSTRATIONS_DIR / "illustrations.csv"
ILLUSTRATION_COLUMNS = [
    "illustration_id",   # <mms_id>_<page>_<NN>, unique across the project
    "mms_id",
    "manuscript_folder",
    "page_number",
    "page_file",         # path of the source page, relative to the project root
    "crop_file",         # path of the cropped image, relative to the project root
    "class",             # CorDeep class name
    "x", "y", "width", "height",   # bounding box in page pixels
    "score",             # detector confidence (0-1)
    "method",            # detector that produced the crop
]


def find_uv() -> str:
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if not Path(uv).exists():
        raise SystemExit("uv not found: install it (https://docs.astral.sh/uv/) and run `uv sync` in external/sphaera-cordeep")
    return uv


def run_cordeep(folder: Path, work_dir: Path, conf: float, device: str) -> Path:
    """Run CorDeep's detect.py on one manuscript folder; return the folder holding its label .txt files."""
    cmd = [find_uv(), "run", "--project", str(CORDEEP_DIR), "python", str(CORDEEP_DIR / "detect.py"),
           "--source", str(folder), "--project", str(work_dir),
           "--save-txt", "--save-conf", "--conf-thres", str(conf), "--device", device]
    result = subprocess.run(cmd, cwd=CORDEEP_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"CorDeep failed on {folder.name}:\n{result.stderr[-2000:]}")
    labels = list(work_dir.glob("*/labels"))
    return labels[0] if labels else work_dir / "no_labels"


def process_manuscript(folder: Path, conf: float, max_area: float, device: str) -> List[dict]:
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    mms_id = meta["mms_id"]
    out_dir = ILLUSTRATIONS_DIR / folder.name
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        labels_dir = run_cordeep(folder, Path(tmp), conf, device)
        for page_file in sorted(folder.glob("*.jpg")):
            label_file = labels_dir / f"{page_file.stem}.txt"
            if not label_file.exists():
                continue
            with Image.open(page_file) as page:
                W, H = page.size
                counters = {}
                for line in label_file.read_text().splitlines():
                    cls, xc, yc, w, h, score = map(float, line.split())
                    if w * h > max_area:
                        continue  # whole page / cover / blank leaf, not an illustration
                    class_name = CORDEEP_CLASSES[int(cls)]
                    slug = class_name.replace(" ", "_").replace("'", "")
                    counters[slug] = counters.get(slug, 0) + 1
                    x, y = round((xc - w / 2) * W), round((yc - h / 2) * H)
                    bw, bh = round(w * W), round(h * H)
                    crop_file = out_dir / f"{page_file.stem}_{slug}_{counters[slug]:02d}.jpg"
                    page.convert("RGB").crop((x, y, x + bw, y + bh)).save(crop_file, quality=95)
                    rows.append({
                        "illustration_id": f"{mms_id}_{page_file.stem}_{slug}_{counters[slug]:02d}",
                        "mms_id": mms_id,
                        "manuscript_folder": folder.name,
                        "page_number": int(page_file.stem),
                        "page_file": page_file.relative_to(PROJECT_ROOT).as_posix(),
                        "crop_file": crop_file.relative_to(PROJECT_ROOT).as_posix(),
                        "class": class_name,
                        "x": x, "y": y, "width": bw, "height": bh,
                        "score": round(score, 4),
                        "method": METHOD,
                    })
    print(f"{folder.name}: {len(rows)} illustrations")
    return rows


def box_overlap(a: dict, b: dict) -> float:
    """Intersection over union of two crops' boxes (0 = apart, 1 = the same box)."""
    ax, ay, aw, ah = (float(a[k]) for k in ("x", "y", "width", "height"))
    bx, by, bw, bh = (float(b[k]) for k in ("x", "y", "width", "height"))
    iw = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / (aw * ah + bw * bh - inter) if inter else 0.0


def drop_duplicate_boxes(rows: List[dict], threshold: float = DUPLICATE_OVERLAP) -> List[dict]:
    """CorDeep can box one drawing twice on a page, often under two classes (e.g. Initial and
    Content Illustration). Keep the more confident box and delete the other crop."""
    by_page = {}
    for r in rows:
        by_page.setdefault((r["manuscript_folder"], str(r["page_number"])), []).append(r)
    kept = []
    for page_rows in by_page.values():
        chosen = []
        for r in sorted(page_rows, key=lambda r: -float(r["score"])):
            if all(box_overlap(r, k) < threshold for k in chosen):
                chosen.append(r)
            else:
                (PROJECT_ROOT / r["crop_file"]).unlink(missing_ok=True)
        kept.extend(chosen)
    order = {id(r): i for i, r in enumerate(rows)}
    return sorted(kept, key=lambda r: order[id(r)])


def main():
    parser = argparse.ArgumentParser(description="Extract illustrations from downloaded manuscripts with CorDeep.")
    parser.add_argument("--only", help="Process a single manuscript folder (by name).")
    parser.add_argument("--conf", type=float, default=0.25, help="Minimum detection confidence (default 0.25).")
    parser.add_argument("--max-area", type=float, default=0.4,
                        help="Drop boxes covering more than this fraction of the page (default 0.4).")
    parser.add_argument("--device", default="mps", help="mps (Apple GPU), cpu, or a CUDA device number.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-extract manuscripts that already have crops (their old crops are removed).")
    args = parser.parse_args()

    if not (CORDEEP_DIR / "detect.py").exists():
        raise SystemExit(f"CorDeep not found in {CORDEEP_DIR} (see README: clone it and run `uv sync` there)")

    # metadata.json is written when step 2 finishes a codex; folders without it are still downloading
    folders = sorted(f for f in MANUSCRIPTS_DIR.iterdir()
                     if f.is_dir() and any(f.glob("*.jpg")) and (f / "metadata.json").exists())
    if args.only:
        folders = [f for f in folders if f.name == args.only]
        if not folders:
            raise SystemExit(f"No manuscript folder with images named {args.only}")

    # keep rows of manuscripts that are not re-processed in this run
    old_rows = []
    if ILLUSTRATIONS_CSV.exists():
        with ILLUSTRATIONS_CSV.open(encoding="utf-8-sig") as f:
            old_rows = list(csv.DictReader(f))

    rows = []
    done = {r["manuscript_folder"] for r in old_rows}
    for folder in folders:
        out_dir = ILLUSTRATIONS_DIR / folder.name
        if folder.name in done or (out_dir.exists() and any(out_dir.iterdir())):
            if not args.overwrite:
                print(f"{folder.name}: already extracted, skipping (use --overwrite to redo)")
                continue
            shutil.rmtree(out_dir)
            old_rows = [r for r in old_rows if r["manuscript_folder"] != folder.name]
        rows.extend(process_manuscript(folder, args.conf, args.max_area, args.device))

    # drop crops whose manuscript folder is gone (e.g. a second photo set of the same manuscript)
    gone = {r["manuscript_folder"] for r in old_rows if not (MANUSCRIPTS_DIR / r["manuscript_folder"]).is_dir()}
    for name in gone:
        print(f"{name}: manuscript folder removed, dropping its crops")
        shutil.rmtree(ILLUSTRATIONS_DIR / name, ignore_errors=True)
    old_rows = [r for r in old_rows if r["manuscript_folder"] not in gone]

    before = len(old_rows) + len(rows)
    all_rows = drop_duplicate_boxes(old_rows + rows)
    if len(all_rows) < before:
        print(f"{before - len(all_rows)} duplicate boxes removed (same drawing boxed twice on a page)")
    ILLUSTRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    with ILLUSTRATIONS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ILLUSTRATION_COLUMNS)
        w.writeheader()
        w.writerows(all_rows)
    print(f"{len(rows)} new crops; {len(all_rows)} rows in {ILLUSTRATIONS_CSV.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
