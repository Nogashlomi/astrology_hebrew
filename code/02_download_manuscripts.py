#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP 2 - Download the digitized copies (IIIF page images) of the chosen manuscripts.

Input:  data/metadata/raw/MANUSCRIPTS_ONLY.csv (every catalogued manuscript and its MARC fields). Each record's
        IIIF manifest is checked live, because Ktiv opens manuscripts over time; the older
        ALL_OPEN_MANUSCRIPTS.csv list (October 2026) missed some that are open now.
Output: data/manuscripts/<mms_id>_<library>_<shelfmark>/NNNN.jpg + metadata.json
        data/metadata/raw/MANUSCRIPTS_IMAGES_INDEX.csv  one row per catalogue record (status, folder, page counts)
        data/metadata/raw/PAGE_LEVEL_METADATA.csv       one row per downloaded page
        data/metadata/raw/DOWNLOAD_FAILURES.csv         what could not be downloaded in the last run, and why
Usage:  python code/02_download_manuscripts.py                 (everything; safe to rerun, skips what is done)
        python code/02_download_manuscripts.py --dry-run       (only report what would be downloaded)
        python code/02_download_manuscripts.py --only <mms_id>
        python code/02_download_manuscripts.py --start 0 --limit 10

How it works:
- Several catalogue records often describe the same physical codex (a parent "קובץ" record plus one
  record per work bound in it). Ktiv gives them the same IIIF manifest, so the codex is downloaded once,
  into the folder of one record (the "owner"); the other records point to that folder in the index CSV
  and are listed in the folder's metadata.json under "other_mms_ids".
- Some manifests list pages whose images are restricted to on-site viewing; the image server answers
  "no permissions". These codices are recorded as "restricted" and no folder is created for them.
- Resumable: a page already on disk is kept only if PAGE_LEVEL_METADATA.csv says it came from the same
  IIIF image; anything else is fetched again. Files are written atomically, so an interrupted run never
  leaves a half-written image.
- Polite: one request at a time, a pause between pages, and a longer back-off when the server says
  it is busy (HTTP 429/503).
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from paths import PROJECT_ROOT, RAW_METADATA_DIR as CSV_DIR, MANUSCRIPTS_DIR as IMAGES_DIR

SLEEP_S = 0.5            # pause after every image request
WIDTH = 1200             # downloaded image width in pixels
TIMEOUT = 60
MAX_ATTEMPTS = 4         # per page
BUSY_WAIT_S = 30         # first back-off when the server is busy; grows with each attempt
MAX_CONSECUTIVE_FAILS = 15   # give up on a codex after this many failed pages in a row
# Ktiv's Cloudflare blocks generic user agents (e.g. curl's); this one is the Sacrobosco project's, which works
USER_AGENT = "HebrewSacroboscoResearch/1.0 (academic research; polite requester)"

INDEX_CSV = CSV_DIR / "MANUSCRIPTS_IMAGES_INDEX.csv"
PAGES_CSV = CSV_DIR / "PAGE_LEVEL_METADATA.csv"
FAILURES_CSV = CSV_DIR / "DOWNLOAD_FAILURES.csv"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """Create clean, safe directory/file names from Hebrew/Latin strings."""
    if not name:
        return "unnamed"
    clean = re.sub(r'[\\/*?:"<>|#=]', '_', name)
    clean = re.sub(r'\s+', '_', clean).strip('_')
    return clean[:40]


LIBRARY_CODES = [  # (substring of the library name, lower case) -> short code; first match wins
    ("france", "BnF"), ("bnf", "BnF"), ("paris", "BnF"),
    ("bavarian", "BSB"), ("munich", "BSB"),
    ("national library of israel", "NLI"),
    ("british", "BL"),
    ("russian state", "RSL"), ("guenzburg", "RSL"),
    ("national library of russia", "NLR"),
    ("palatina", "Palatina"), ("parma", "Palatina"),
    ("theological", "JTS"), ("jts", "JTS"),
    ("hebrew union", "HUC"), ("huc", "HUC"),
    ("ets haim", "EtsHaim"),
    ("berlin", "Berlin"),
    ("hungarian", "Budapest"),
    ("oriental", "IOM"), ("petersburg", "IOM"),
    ("vatican", "Vatican"),
    ("bodleian", "Bodleian"), ("oxford", "Bodleian"),
    ("laurentian", "Laurenziana"),
    ("ambrosian", "Ambrosiana"),
    ("mantua", "Mantua"),
    ("leipzig", "Leipzig"),
    ("austrian", "ONB"),
    ("hamburg", "Hamburg"),
    ("national central library of fl", "BNCF"),
    ("columbia", "Columbia"),
    ("cambridge", "Cambridge"),
    ("national academ", "NatAcad"),
    ("bar-ilan", "BarIlan"),
    ("leiden", "Leiden"),
    ("ringelblum", "Ringelblum"),
    ("victor emmanuel", "BNN"),
    ("state library victoria", "SLV"),
    ("beth din", "BethDin"),
    ("montefiore", "Montefiore"),
    ("katz", "Penn"),
    ("johann christian senckenberg", "Frankfurt"),
]


def get_library_code(lib_name: str) -> str:
    """Short code for manuscript libraries."""
    lib = (lib_name or "").lower()
    for key, code in LIBRARY_CODES:
        if key in lib:
            return code
    return sanitize_filename(lib_name)[:10]


def safe_str(val, max_len=None):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return s[:max_len] if max_len else s


def first_value(val) -> str:
    """MARC fields with several values are joined with ' | '; take the first."""
    return safe_str(val).split("|")[0].strip()


def fetch_manifest(mms_id: str, session: requests.Session):
    """Fetch the IIIF manifest (direct endpoint first, then DOCID). Returns (url, manifest, canvases)."""
    urls = [
        f"https://iiif.nli.org.il/IIIFv21/{mms_id}/manifest",
        f"https://iiif.nli.org.il/IIIFv21/DOCID/PNX_MANUSCRIPTS{mms_id}/manifest",
    ]
    for url in urls:
        for attempt in range(1, 4):
            try:
                r = session.get(url, timeout=TIMEOUT)
                if r.status_code in (429, 503):
                    time.sleep(BUSY_WAIT_S * attempt)
                    continue
                if r.status_code == 200:
                    man = r.json()
                    seq = man.get("sequences", [])
                    if seq and seq[0].get("canvases"):
                        return url, man, seq[0]["canvases"]
                    if man.get("items"):
                        return url, man, man["items"]
                break
            except Exception:
                time.sleep(2 * attempt)
        time.sleep(SLEEP_S)
    return None, None, []


def image_service(cv: dict):
    """IIIF image service base URL of one canvas (IIIF v2 or v3)."""
    try:
        if cv.get("images"):
            svc = cv["images"][0]["resource"].get("service", {})
            svc = svc[0] if isinstance(svc, list) else svc
            return svc.get("@id") or svc.get("id")
        if cv.get("items"):
            body = cv["items"][0]["items"][0]["body"]
            svc = body.get("service", [{}])[0]
            return svc.get("id") or svc.get("@id")
    except (KeyError, IndexError, TypeError):
        pass
    return None


def label_text(label) -> str:
    if isinstance(label, dict):  # IIIF v3 language map
        label = next(iter(label.values()), [""])
    if isinstance(label, list):
        label = label[0] if label else ""
    return str(label)


def fetch_image(url: str, session: requests.Session):
    """Download one image. Returns (bytes, None) or (None, error). error 'restricted' = no permission."""
    error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ctype.startswith("image") and resp.content[:2] == b"\xff\xd8":
                return resp.content, None
            if "no permissions" in resp.text[:500] or "unauthorized" in resp.text[:500]:
                return None, "restricted"
            error = f"HTTP {resp.status_code} {ctype.split(';')[0]}"
            if resp.status_code in (429, 503):
                wait = int(resp.headers.get("Retry-After", BUSY_WAIT_S * attempt))
                print(f"    server busy ({resp.status_code}), waiting {wait}s")
                time.sleep(wait)
                continue
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)[:120]}"
        time.sleep(2 * attempt)
    return None, error


def load_csv(path: Path):
    return pd.read_csv(path, dtype=str).fillna("").to_dict("records") if path.exists() else []


def save_csv(rows, path: Path):
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def existing_folder(mms_id: str):
    hits = sorted(IMAGES_DIR.glob(f"{mms_id}_*"))
    return hits[0] if hits else None


def collect_codices(merged: pd.DataFrame, session: requests.Session):
    """Fetch every manifest and group the catalogue records by physical codex (same page images)."""
    codices = {}
    unavailable = []
    for n, (_, row) in enumerate(merged.iterrows(), 1):
        rec = row.to_dict()
        mms_id = str(rec["mms_id"])
        url, man, canvases = fetch_manifest(mms_id, session)
        parent = safe_str(rec.get("773$w"))
        if not canvases and parent and parent != mms_id:
            url, man, canvases = fetch_manifest(parent, session)
        services = [image_service(cv) for cv in canvases]
        print(f"  manifest {n}/{len(merged)} {mms_id}: {len(canvases)} pages")
        if not canvases or not services[0]:
            unavailable.append((rec, url))
            continue
        key = services[0]
        codex = codices.setdefault(key, {"records": [], "manifest": man, "manifest_url": url,
                                         "canvases": canvases, "services": services})
        codex["records"].append(rec)
    return merge_same_shelfmark(codices), unavailable


def merge_same_shelfmark(codices):
    """Ktiv sometimes holds two photographic sets of one manuscript (e.g. RSL Guenzburg 274), attached to
    different catalogue records. Their images differ, so they are joined by library + shelfmark instead.
    The set linked to more catalogue records is kept; the other set's records point to it."""
    merged = {}
    owner_of_mark = {}
    for key, codex in sorted(codices.items(), key=lambda kv: -len(kv[1]["records"])):
        marks = {record_fields(r)[1:] for r in codex["records"]}
        target = next((owner_of_mark[m] for m in marks if m in owner_of_mark), None)
        if target is None:
            merged[key] = codex
            for m in marks:
                owner_of_mark[m] = key
        else:
            print(f"  same shelfmark, second photo set skipped: {', '.join(str(r['mms_id']) for r in codex['records'])}")
            merged[target]["records"].extend(codex["records"])
    return merged


def choose_owner(records):
    """The record whose MMS ID names the folder: one already downloaded, else a work rather than
    the parent miscellany ('קובץ'), else the first."""
    for rec in records:
        if existing_folder(rec["mms_id"]):
            return rec
    for rec in records:
        if not str(rec.get("title", "")).startswith("קובץ"):
            return rec
    return records[0]


def record_fields(rec):
    lib = first_value(rec.get("710$a")) or first_value(rec.get("942$a")) or safe_str(rec.get("library")) or "Unknown"
    shelfmark = first_value(rec.get("942$z")) or first_value(rec.get("090$a")) or "ms"
    return lib, get_library_code(lib), shelfmark


def manifest_license(man):
    lic = man.get("license") or ""
    lic = lic[0] if isinstance(lic, list) and lic else lic
    attr = man.get("attribution") or ""
    attr = attr[0] if isinstance(attr, list) and attr else attr
    return str(lic), str(attr)


def download_codex(codex, session, trusted_pages, failures):
    """Download every page of one codex into its owner's folder. Returns (status, folder, page_rows)."""
    records = codex["records"]
    owner = choose_owner(records)
    mms_id = str(owner["mms_id"])
    lib, lib_code, shelfmark = record_fields(owner)
    canvases, services = codex["canvases"], codex["services"]
    total = len(canvases)

    target_dir = existing_folder(mms_id) or IMAGES_DIR / f"{mms_id}_{lib_code}_{sanitize_filename(shelfmark)}"
    print(f"\n=== {mms_id} | {lib_code}: {shelfmark} | {total} pages | {target_dir.name}")
    others = [str(r["mms_id"]) for r in records if str(r["mms_id"]) != mms_id]
    if others:
        print(f"    same codex as: {', '.join(others)}")

    # Check access with the first page before creating anything on disk
    first_url = f"{services[0]}/full/{WIDTH},/0/default.jpg"
    first_file = target_dir / "0001.jpg"
    if trusted_pages.get(str(first_file.relative_to(PROJECT_ROOT))) != first_url or not first_file.exists():
        data, err = fetch_image(first_url, session)
        time.sleep(SLEEP_S)
        if err == "restricted":
            print("    images restricted (no permission on the image server) - skipped")
            failures.append({"mms_id": mms_id, "folder": "", "page_number": "", "url": first_url,
                             "error": "restricted: image server refuses access (on-site viewing only)"})
            return "restricted", None, []
        if data is None:
            print(f"    first page failed: {err} - skipped")
            failures.append({"mms_id": mms_id, "folder": "", "page_number": 1, "url": first_url, "error": err})
            return "failed", None, []
        target_dir.mkdir(parents=True, exist_ok=True)
        write_atomic(first_file, data)

    page_rows, saved, fails_in_row = [], 0, 0
    for i, (cv, base) in enumerate(zip(canvases, services), 1):
        file_name = f"{i:04d}.jpg"
        file_path = target_dir / file_name
        rel = str(file_path.relative_to(PROJECT_ROOT))
        img_url = f"{base}/full/{WIDTH},/0/default.jpg" if base else ""
        ok = False
        if not base:
            failures.append({"mms_id": mms_id, "folder": target_dir.name, "page_number": i, "url": "",
                             "error": "no image service in manifest"})
        elif file_path.exists() and (i == 1 or trusted_pages.get(rel) == img_url):
            ok = True
        else:
            data, err = fetch_image(img_url, session)
            if data is not None:
                write_atomic(file_path, data)
                ok = True
            else:
                failures.append({"mms_id": mms_id, "folder": target_dir.name, "page_number": i,
                                 "url": img_url, "error": err})
                print(f"    page {i} failed: {err}")
            time.sleep(SLEEP_S)

        if ok:
            saved += 1
            fails_in_row = 0
            page_rows.append({
                "mms_id": mms_id, "library_code": lib_code, "shelfmark": shelfmark,
                "page_number": i, "canvas_label": label_text(cv.get("label", f"Page {i}")),
                "file_name": file_name, "relative_path": rel,
                "width": cv.get("width"), "height": cv.get("height"), "iiif_image_url": img_url,
            })
        else:
            fails_in_row += 1
            if fails_in_row >= MAX_CONSECUTIVE_FAILS:
                print(f"    {fails_in_row} pages failed in a row - stopping this codex, rerun later")
                break
        if i % 25 == 0 or i == total:
            print(f"    {i}/{total} pages ({saved} saved)")

    lic, attr = manifest_license(codex["manifest"])
    meta_doc = {
        "mms_id": mms_id,
        "other_mms_ids": others,
        "title": safe_str(owner.get("title")) or safe_str(owner.get("ms_title")),
        "shelfmark": shelfmark,
        "holding_library": lib,
        "library_code": lib_code,
        "date_place": safe_str(owner.get("ms_date_place")),
        "script": safe_str(owner.get("958$a")),
        "colophon": safe_str(owner.get("957$a")),
        "total_pages": total,
        "downloaded_pages": saved,
        "manifest_url": codex["manifest_url"],
        "license": lic,
        "attribution": attr,
        "folder_name": target_dir.name,
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    (target_dir / "metadata.json").write_text(json.dumps(meta_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    status = "complete" if saved == total else "partial"
    return status, target_dir, page_rows


def write_atomic(path: Path, data: bytes):
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def index_row(rec, codex, owner_id, status, folder, saved):
    lib, lib_code, shelfmark = record_fields(rec)
    lic = manifest_license(codex["manifest"])[0] if codex else ""
    return {
        "mms_id": str(rec["mms_id"]),
        "library_code": lib_code,
        "shelfmark": shelfmark,
        "title": safe_str(rec.get("title")) or safe_str(rec.get("ms_title")),
        "status": status,
        "folder_path": str(folder.relative_to(PROJECT_ROOT)) if folder else "",
        "same_codex_as": owner_id if owner_id != str(rec["mms_id"]) else "",
        "total_canvases": len(codex["canvases"]) if codex else 0,
        "downloaded_pages": saved,
        "manifest_url": codex["manifest_url"] if codex else "",
        "license": lic.rsplit("/", 1)[-1],
        "date_place": safe_str(rec.get("ms_date_place")),
        "script": safe_str(rec.get("958$a")),
        "colophon": safe_str(rec.get("957$a"), 100),
    }


def main():
    parser = argparse.ArgumentParser(description="Download open Hebrew astrology manuscripts.")
    parser.add_argument("--start", type=int, default=0, help="First codex to process (0-based).")
    parser.add_argument("--limit", type=int, default=None, help="Number of codices to process.")
    parser.add_argument("--only", help="Process only the codex containing this MMS ID.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch manifests and report; download nothing.")
    args = parser.parse_args()

    merged = pd.read_csv(CSV_DIR / "MANUSCRIPTS_ONLY.csv", dtype=str)
    merged["mms_id"] = merged["ms_mms_id"]
    merged["title"] = merged["ms_title"]
    merged = merged.drop_duplicates(subset=["mms_id"]).reset_index(drop=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    print(f"Fetching IIIF manifests for {len(merged)} catalogue records...")
    codices, unavailable = collect_codices(merged, session)
    keys = list(codices)
    if args.only:
        keys = [k for k in keys if any(str(r["mms_id"]) == args.only for r in codices[k]["records"])]
    keys = keys[args.start: args.start + args.limit if args.limit is not None else None]

    print(f"\n{len(merged)} records -> {len(codices)} distinct codices "
          f"({sum(len(c['canvases']) for c in codices.values())} pages); "
          f"{len(unavailable)} records without pages in their manifest")
    print(f"Processing {len(keys)} codices | width {WIDTH}px | pause {SLEEP_S}s")
    if args.dry_run:
        return

    index_rows = {r["mms_id"]: r for r in load_csv(INDEX_CSV)}

    # Outage guard: if far fewer records have pages than last time, Ktiv is probably down (e.g. Cloudflare
    # error 520); stop before the index is overwritten with "no pages".
    had_pages = sum(1 for r in index_rows.values() if r.get("status") in ("complete", "partial", "restricted"))
    have_pages = len(merged) - len(unavailable)
    if not args.only and had_pages and have_pages < 0.5 * had_pages:
        raise SystemExit(f"Only {have_pages} records have pages now, against {had_pages} last time: Ktiv seems "
                         f"unavailable. Nothing was changed; try again later.")
    page_rows = load_csv(PAGES_CSV)
    trusted_pages = {r["relative_path"]: r["iiif_image_url"] for r in page_rows}
    failures = []

    for rec, url in unavailable:
        index_rows[str(rec["mms_id"])] = index_row(rec, None, str(rec["mms_id"]), "no_pages_in_manifest", None, 0)
        failures.append({"mms_id": str(rec["mms_id"]), "folder": "", "page_number": "", "url": url or "",
                         "error": "manifest has no pages (restricted or not digitized)"})

    for n, key in enumerate(keys, 1):
        codex = codices[key]
        print(f"\n>>> [{n}/{len(keys)}]")
        status, folder, rows = download_codex(codex, session, trusted_pages, failures)
        owner_id = str(choose_owner(codex["records"])["mms_id"])
        for rec in codex["records"]:
            index_rows[str(rec["mms_id"])] = index_row(rec, codex, owner_id, status, folder, len(rows))
        # Replace this codex's page rows (none are left for a restricted codex)
        codex_ids = {str(r["mms_id"]) for r in codex["records"]}
        page_rows = [p for p in page_rows if p["mms_id"] not in codex_ids] + rows
        # Persist after every codex so an interrupted run loses nothing
        save_csv(list(index_rows.values()), INDEX_CSV)
        save_csv(page_rows, PAGES_CSV)
        save_csv([dict(f, time=datetime.now().isoformat(timespec="seconds")) for f in failures], FAILURES_CSV)

    save_csv(list(index_rows.values()), INDEX_CSV)
    save_csv([dict(f, time=datetime.now().isoformat(timespec="seconds")) for f in failures], FAILURES_CSV)
    statuses = pd.Series([r.get("status", "") for r in index_rows.values()]).value_counts()
    print("\n========================================================")
    print("BATCH FINISHED")
    print(f"Records by status:\n{statuses.to_string()}")
    print(f"Pages indexed: {len(page_rows)} | failures logged: {len(failures)} -> {FAILURES_CSV.name}")
    print("========================================================")


if __name__ == "__main__":
    main()
