#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP 3 - Organize the metadata into what the visualizer needs.

Joins the catalogue with the page index and the downloaded folders, extracts people, centuries,
scripts and places (from the coordinate table below), and writes one clean JSON file.

Input:  data/metadata/raw/MANUSCRIPTS_ONLY.csv (the corpus chosen in step 1), PAGE_LEVEL_METADATA.csv,
        MANUSCRIPTS_IMAGES_INDEX.csv (same_codex_as: records that share a downloaded codex)
        All but the first are written by step 2; without them every record is shown without images.
        data/manuscripts/
Output: data/metadata/clean/visualizer_data.json
"""

import json
import re
import sys
from pathlib import Path
import pandas as pd

from paths import PROJECT_ROOT, RAW_METADATA_DIR as CSV_DIR, MANUSCRIPTS_DIR as IMAGES_DIR, CLEAN_METADATA_DIR

OUTPUT_JSON = CLEAN_METADATA_DIR / "visualizer_data.json"

# Coordinates dictionary for historical places and library cities
COORDINATES = {
    # Places of writing / origin
    "Venice (Italy)": {"lat": 45.4408, "lon": 12.3155, "label": "Venice, Italy (ונציה)"},
    "Vienna (Austria)": {"lat": 48.2082, "lon": 16.3738, "label": "Vienna, Austria (וינה)"},
    "Prague (Czech Republic)": {"lat": 50.0755, "lon": 14.4378, "label": "Prague, Czech Republic (פראג)"},
    "Mantua (Italy)": {"lat": 45.1564, "lon": 10.7914, "label": "Mantua, Italy (מנטובה)"},
    "Mantua": {"lat": 45.1564, "lon": 10.7914, "label": "Mantua, Italy (מנטובה)"},
    "Thessalonikē (Greece)": {"lat": 40.6401, "lon": 22.9444, "label": "Thessaloniki, Greece (שאלוניקי)"},
    "Ascoli Piceno (Italy)": {"lat": 42.8548, "lon": 13.5750, "label": "Ascoli Piceno, Italy (אסקולי פיצ'נו)"},
    "Worms (Germany)": {"lat": 49.6341, "lon": 8.3615, "label": "Worms, Germany (וורמס)"},
    "Frankfurt (Oder) (Germany)": {"lat": 52.3424, "lon": 14.5505, "label": "Frankfurt (Oder), Germany (פרנקפורט דאודר)"},
    "Benevento (Italy)": {"lat": 41.1306, "lon": 14.7818, "label": "Benevento, Italy (בנוונטו)"},
    "Budapest (Hungary)": {"lat": 47.4979, "lon": 19.0402, "label": "Budapest, Hungary (בודפשט)"},
    "Nușeni (Romania)": {"lat": 47.1000, "lon": 24.3167, "label": "Nuşeni, Romania (נושני)"},
    "Krakow (Poland)": {"lat": 50.0647, "lon": 19.9450, "label": "Krakow, Poland (קרקוב)"},
    "Constantinople": {"lat": 41.0082, "lon": 28.9784, "label": "Constantinople / Istanbul (קושטא)"},
    "Rome (Italy)": {"lat": 41.9028, "lon": 12.4964, "label": "Rome, Italy (רומא)"},
    "Paris (France)": {"lat": 48.8566, "lon": 2.3522, "label": "Paris, France (פריז)"},
    
    # Holding library locations
    "Oxford": {"lat": 51.7520, "lon": -1.2577, "label": "Oxford, UK (Bodleian Library)"},
    "Paris": {"lat": 48.8566, "lon": 2.3522, "label": "Paris, France (BnF)"},
    "Jerusalem": {"lat": 31.7683, "lon": 35.2137, "label": "Jerusalem (National Library of Israel)"},
    "Moscow": {"lat": 55.7558, "lon": 37.6173, "label": "Moscow, Russia (Russian State Library)"},
    "New York, NY": {"lat": 40.7128, "lon": -74.0060, "label": "New York, NY (JTS / Columbia)"},
    "London": {"lat": 51.5074, "lon": -0.1278, "label": "London, UK (British Library)"},
    "Florence": {"lat": 43.7696, "lon": 11.2558, "label": "Florence, Italy (Biblioteca Medicea Laurenziana)"},
    "Munich": {"lat": 48.1351, "lon": 11.5820, "label": "Munich, Germany (Bayerische Staatsbibliothek)"},
    "Parma": {"lat": 44.8015, "lon": 10.3279, "label": "Parma, Italy (Biblioteca Palatina)"},
    "Berlin": {"lat": 52.5200, "lon": 13.4050, "label": "Berlin, Germany (Staatsbibliothek zu Berlin)"},
    "Cambridge": {"lat": 52.2053, "lon": 0.1218, "label": "Cambridge, UK (Cambridge University Library)"},
    "Vatican City": {"lat": 41.9029, "lon": 12.4534, "label": "Vatican City (Biblioteca Apostolica Vaticana)"},
    "St. Petersburg": {"lat": 59.9343, "lon": 30.3351, "label": "St. Petersburg, Russia (IOM / NLR)"},
    "Vienna": {"lat": 48.2082, "lon": 16.3738, "label": "Vienna, Austria (ÖNB)"},
    "Budapest": {"lat": 47.4979, "lon": 19.0402, "label": "Budapest, Hungary (HAS Library)"},
    "Leipzig": {"lat": 51.3397, "lon": 12.3731, "label": "Leipzig, Germany (Leipzig University)"},
    "Hamburg": {"lat": 53.5511, "lon": 9.9937, "label": "Hamburg, Germany (SUB Hamburg)"},
    "Frankfurt am Main": {"lat": 50.1109, "lon": 8.6821, "label": "Frankfurt am Main, Germany (UB Frankfurt)"},
    "Philadelphia, PA": {"lat": 39.9526, "lon": -75.1652, "label": "Philadelphia, PA (Katz Center / UPenn)"},
    "Amsterdam": {"lat": 52.3676, "lon": 4.9041, "label": "Amsterdam, Netherlands (Ets Haim)"},

    # Places of writing added for the astrology corpus
    "Montpellier (France)": {"lat": 43.6108, "lon": 3.8767, "label": "Montpellier, France (מונפשליר)"},
    "Alès (France)": {"lat": 44.1250, "lon": 4.0817, "label": "Alès, France"},
    "Taza (Taza, Morocco)": {"lat": 34.2100, "lon": -4.0100, "label": "Taza, Morocco"},
    "Lisbon (Portugal)": {"lat": 38.7223, "lon": -9.1393, "label": "Lisbon, Portugal (ליסבון)"},
    "Thebes (Greece)": {"lat": 38.3250, "lon": 23.3190, "label": "Thebes, Greece (תיבי)"},
    "Toledo (Spain)": {"lat": 39.8628, "lon": -4.0273, "label": "Toledo, Spain (טולדו)"},
    "Casale Monferrato (Italy)": {"lat": 45.1336, "lon": 8.4526, "label": "Casale Monferrato, Italy"},
    "Rodez (France)": {"lat": 44.3506, "lon": 2.5750, "label": "Rodez, France"},
    "Bari (Italy)": {"lat": 41.1171, "lon": 16.8719, "label": "Bari, Italy"},
    "Montepulciano (Italy)": {"lat": 43.0928, "lon": 11.7808, "label": "Montepulciano, Italy"},
    "Ferrara (Italy)": {"lat": 44.8381, "lon": 11.6198, "label": "Ferrara, Italy (פירארה)"},
    "Lucca (Italy)": {"lat": 43.8429, "lon": 10.5027, "label": "Lucca, Italy"},
    "Burgos (Spain)": {"lat": 42.3439, "lon": -3.6969, "label": "Burgos, Spain"},
    "Perugia (Italy)": {"lat": 43.1107, "lon": 12.3908, "label": "Perugia, Italy"},
    "Tarquinia (Italy)": {"lat": 42.2540, "lon": 11.7580, "label": "Tarquinia (Corneto), Italy"},
    "Tripoli (Libya)": {"lat": 32.8872, "lon": 13.1913, "label": "Tripoli, Libya"},
    "Lecce (Italy)": {"lat": 40.3515, "lon": 18.1750, "label": "Lecce, Italy"},
    "Ohrid (North Macedonia)": {"lat": 41.1172, "lon": 20.8016, "label": "Ohrid, North Macedonia"},
    "Huesca (Spain)": {"lat": 42.1401, "lon": -0.4089, "label": "Huesca, Spain"},
    "Syracuse (Italy)": {"lat": 37.0755, "lon": 15.2866, "label": "Syracuse, Sicily"},
    "Coburg (Germany)": {"lat": 50.2612, "lon": 10.9627, "label": "Coburg, Germany"},
    "Forlì (Italy)": {"lat": 44.2227, "lon": 12.0407, "label": "Forlì, Italy"},
    "Saint Petersburg (Russia)": {"lat": 59.9343, "lon": 30.3351, "label": "St. Petersburg, Russia"},
    "Istanbul (Turkey)": {"lat": 41.0082, "lon": 28.9784, "label": "Constantinople / Istanbul (קושטא)"},
    "Narbonne (France)": {"lat": 43.1843, "lon": 3.0036, "label": "Narbonne, France (נרבונה)"},
    "Villefort (Lozère, France : Canton)": {"lat": 44.4400, "lon": 3.9330, "label": "Villefort, France"},
    "Volterra (Italy)": {"lat": 43.4020, "lon": 10.8610, "label": "Volterra, Italy"},
    "Zaragoza (Spain)": {"lat": 41.6488, "lon": -0.8891, "label": "Zaragoza, Spain (סרגוסה)"},
    "Spoleto (Italy)": {"lat": 42.7340, "lon": 12.7380, "label": "Spoleto, Italy"},
    "Coimbra (Portugal)": {"lat": 40.2033, "lon": -8.4103, "label": "Coimbra, Portugal"},
    "Imola (Italy)": {"lat": 44.3530, "lon": 11.7140, "label": "Imola, Italy"},
    "Acre (Israel)": {"lat": 32.9281, "lon": 35.0820, "label": "Acre (עכו)"},
    "Hebron (West Bank)": {"lat": 31.5326, "lon": 35.0998, "label": "Hebron (חברון)"},
    "Tlemcen (Algeria)": {"lat": 34.8828, "lon": -1.3167, "label": "Tlemcen, Algeria"},
    "Catania (Italy)": {"lat": 37.5079, "lon": 15.0830, "label": "Catania, Sicily"},
    "Sicily (Italy)": {"lat": 37.6000, "lon": 14.0154, "label": "Sicily (region)"},
    "Oria (Italy)": {"lat": 40.4990, "lon": 17.6400, "label": "Oria, Italy"},
    "Seville (Spain)": {"lat": 37.3891, "lon": -5.9845, "label": "Seville, Spain (שבילייה)"},
    "Majorca (Spain)": {"lat": 39.5696, "lon": 2.6502, "label": "Majorca, Spain (מיורקה)"},
    "Auxerre (France)": {"lat": 47.7986, "lon": 3.5673, "label": "Auxerre, France"},

    # Holding library cities added for the astrology corpus
    "Madrid": {"lat": 40.4168, "lon": -3.7038, "label": "Madrid, Spain"},
    "Basel": {"lat": 47.5596, "lon": 7.5886, "label": "Basel, Switzerland"},
    "Halle an der Saale": {"lat": 51.4825, "lon": 11.9697, "label": "Halle, Germany"},
    "Geneva": {"lat": 46.2044, "lon": 6.1432, "label": "Geneva, Switzerland"},
    "Boston, MA": {"lat": 42.3601, "lon": -71.0589, "label": "Boston, MA"},
    "Nonantola": {"lat": 44.6780, "lon": 11.0420, "label": "Nonantola, Italy"},
    "Modena": {"lat": 44.6471, "lon": 10.9252, "label": "Modena, Italy"},
    "Dresden": {"lat": 51.0504, "lon": 13.7373, "label": "Dresden, Germany (SLUB)"},
    "Zurich": {"lat": 47.3769, "lon": 8.5417, "label": "Zurich, Switzerland"},
    "Holon": {"lat": 32.0158, "lon": 34.7874, "label": "Holon, Israel"},
    "Berne": {"lat": 46.9480, "lon": 7.4474, "label": "Bern, Switzerland"},
    "Leiden": {"lat": 52.1601, "lon": 4.4970, "label": "Leiden, Netherlands (Leiden University)"},
    "Chicago, IL": {"lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL"},
    "Ferrara": {"lat": 44.8381, "lon": 11.6198, "label": "Ferrara, Italy"},
    "Naples": {"lat": 40.8518, "lon": 14.2681, "label": "Naples, Italy"},
    "San Lorenzo del Escorial": {"lat": 40.5891, "lon": -4.1477, "label": "El Escorial, Spain"},
    "Darmstadt": {"lat": 49.8728, "lon": 8.6512, "label": "Darmstadt, Germany"},
    "Warsaw": {"lat": 52.2297, "lon": 21.0122, "label": "Warsaw, Poland"},
    "Wrocław": {"lat": 51.1079, "lon": 17.0385, "label": "Wrocław, Poland"},
    "Birmingham, AL": {"lat": 33.5186, "lon": -86.8104, "label": "Birmingham, AL"},
    "Livorno": {"lat": 43.5485, "lon": 10.3106, "label": "Livorno, Italy"},
}


CENTURY_LABELS = {n: f"{n}th Century ({(n - 1) * 100 + 1}–{n * 100})" for n in range(11, 21)}
HEBREW_CENTURIES = {'י"א': 11, 'י"ב': 12, 'י"ג': 13, 'י"ד': 14, 'ט"ו': 15, 'ט"ז': 16, 'י"ז': 17, 'י"ח': 18,
                    'י"ט': 19, "כ'": 20}


def parse_century(date_str: str) -> str:
    """Century bucket of a date string: the Gregorian year in brackets if there is one, else the first
    (earliest) Hebrew century named, so 'מאה י"ד-ט"ו' counts as 14th century."""
    if not date_str or pd.isna(date_str):
        return "Unknown Era"
    s = str(date_str)
    match_year = re.search(r'\((\d{4})', s)
    if match_year:
        return CENTURY_LABELS.get((int(match_year.group(1)) - 1) // 100 + 1, "Unknown Era")
    found = [(s.find(k), n) for k, n in HEBREW_CENTURIES.items() if k in s]
    return CENTURY_LABELS[min(found)[1]] if found else "Unknown Era"


def extract_year(date_str: str):
    """Extract 4-digit Gregorian year if found."""
    if not date_str or pd.isna(date_str):
        return None
    match = re.search(r'\((\d{4})\)', str(date_str))
    return int(match.group(1)) if match else None


def clean_field(val):
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()


# Titles such as 'חבור באסטרולוגיה' or 'לקוטים באסטרולוגיה' describe an unidentified work; they are listed
# together under one name in the Included Texts tab.
GENERIC_TITLE = re.compile(r"^(חבור|חבורים|חיבור|חיבורים|עניני|ענייני|לקוטים|ליקוטים|קטעים|קטע)\s*(ב|של\s*)?"
                           r"(אסטרולוגיה|אסטרונומיה ואסטרולוגיה|אסטרולוגיה ואסטרונומיה)?$")
UNIDENTIFIED_TEXT = "חבור לא מזוהה באסטרולוגיה (unidentified astrological text)"


def normalize_text_title(title: str):
    """'ספר המולדות (קטע).' -> ('ספר המולדות', True). Returns (None, False) for miscellany titles."""
    t = re.sub(r"[\s.:;,/]+$", "", title.strip())
    fragment = "קטע" in t
    t = re.sub(r"\s*\([^)]*\)", "", t).strip(" .:;,")
    if not t or t.startswith(("קובץ", "קבץ")):
        return None, False
    if GENERIC_TITLE.match(t):     # a cataloguer's description, not the name of a work
        return UNIDENTIFIED_TEXT, fragment
    return t, fragment


def build_codices_and_texts(manuscripts, index_csv):
    """Group catalogue records into physical manuscripts (codices) and list the texts each contains.

    Records belong to one codex when one is the parent volume of the other (MARC 773$w), when they share
    downloaded page images (step 2's same_codex_as), or when they have the same library and shelfmark.
    Texts come from each record's own title (a work inside the volume) and its added titles (MARC 740$a);
    miscellany titles ('קובץ ...') describe the volume, not a text.
    """
    parent = {m["mms_id"]: m["mms_id"] for m in manuscripts}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_mark = {}
    for m in manuscripts:
        if m["parent_mms"] and m["parent_mms"] != m["mms_id"]:
            union(m["parent_mms"], m["mms_id"])
        mark = (m["library"].split("|")[0].strip(), m["shelfmark"].split("|")[0].strip())
        if mark[1] and mark[1] != "Shelfmark Not Recorded":
            if mark in by_mark:
                union(by_mark[mark], m["mms_id"])
            else:
                by_mark[mark] = m["mms_id"]
    if index_csv.exists():
        idx = pd.read_csv(index_csv, dtype=str).fillna("")
        if "same_codex_as" in idx.columns:
            for _, r in idx[idx["same_codex_as"] != ""].iterrows():
                union(r["same_codex_as"], r["mms_id"])

    groups = {}
    for m in manuscripts:
        groups.setdefault(find(m["mms_id"]), []).append(m)

    codices, texts = [], {}
    for members in groups.values():
        # the volume record (no parent of its own) describes the codex best; else the first record
        main = next((m for m in members if not m["parent_mms"]), members[0])
        codex_id = main["mms_id"]
        years = [m["year"] for m in members if m["year"]]
        centuries = [m["century"] for m in members if m["century"] and m["century"] != "Unknown Era"]
        with_images = next((m for m in members if m["has_local_images"]), None)
        codex_texts = {}
        for m in members:
            m["codex_id"] = codex_id
            for raw in [m["title"]] + m["added_titles"]:
                name, fragment = normalize_text_title(raw)
                if name:
                    entry = codex_texts.setdefault(name, {"title": name, "fragment": fragment, "records": []})
                    entry["fragment"] = entry["fragment"] and fragment
                    if m["mms_id"] not in entry["records"]:
                        entry["records"].append(m["mms_id"])
        codices.append({
            "codex_id": codex_id,
            "shelfmark": main["shelfmark"].split("|")[0].strip(),
            "library": main["library"].split("|")[0].strip(),
            "library_city": main["library_city"],
            "title": main["title"],
            "century": centuries[0] if centuries else "Unknown Era",
            "year": min(years) if years else None,
            "place_writing": next((m["place_writing"] for m in members if m["place_writing"]), ""),
            "script": next((m["script"] for m in members if m["script"] and m["script"] != "Not Specified"), ""),
            "records": [m["mms_id"] for m in members],
            "has_images": with_images is not None,
            "image_record": with_images["mms_id"] if with_images else "",
            "texts": sorted(codex_texts),
            "contents": next((m["contents"] for m in members if m["contents"]), ""),
        })
        for name, entry in codex_texts.items():
            t = texts.setdefault(name, {"title": name, "codices": [], "fragment_in": []})
            t["codices"].append(codex_id)
            if entry["fragment"]:
                t["fragment_in"].append(codex_id)

    text_list = sorted(texts.values(), key=lambda t: (-len(t["codices"]), t["title"]))
    for t in text_list:
        t["count"] = len(t["codices"])
    codices.sort(key=lambda c: (c["year"] or 9999, c["shelfmark"]))
    return codices, text_list


def build_data():
    print("Reading catalogue and image data...")
    ms_csv = CSV_DIR / "MANUSCRIPTS_ONLY.csv"
    if not ms_csv.exists():
        print("MANUSCRIPTS_ONLY.csv not found!")
        sys.exit(1)
        
    df = pd.read_csv(ms_csv, dtype=str)
    
    # Read page level metadata if present
    page_meta_csv = CSV_DIR / "PAGE_LEVEL_METADATA.csv"
    df_pages = pd.read_csv(page_meta_csv, dtype=str) if page_meta_csv.exists() else pd.DataFrame()
    
    # Index pages by MMS ID
    pages_by_mms = {}
    if not df_pages.empty:
        for mms_id, group in df_pages.groupby("mms_id"):
            pages_by_mms[str(mms_id)] = group.to_dict("records")
            
    # Also inspect data/manuscripts/ directly (folder names start with the MMS ID)
    local_manuscript_dirs = {}
    if IMAGES_DIR.exists():
        for f in IMAGES_DIR.iterdir():
            if f.is_dir() and not f.name.startswith("."):
                mms_part = f.name.split("_")[0]
                local_manuscript_dirs[mms_part] = f

    # Records that share a codex with a downloaded record (step 2's same_codex_as) use its folder and pages
    index_csv = CSV_DIR / "MANUSCRIPTS_IMAGES_INDEX.csv"
    if index_csv.exists():
        df_index = pd.read_csv(index_csv, dtype=str).fillna("")
        if "same_codex_as" in df_index.columns:
            for _, r in df_index[df_index["same_codex_as"] != ""].iterrows():
                owner = r["same_codex_as"]
                if owner in local_manuscript_dirs:
                    local_manuscript_dirs[r["mms_id"]] = local_manuscript_dirs[owner]
                    pages_by_mms[r["mms_id"]] = pages_by_mms.get(owner, [])

        
    manuscripts = []
    persons_map = {}
    places_writing_map = {}
    places_holding_map = {}
    queries_map = {}
    century_map = {}
    script_map = {}

    for _, row in df.iterrows():
        mms_id = clean_field(row.get("ms_mms_id"))
        if not mms_id:
            continue
            
        title = clean_field(row.get("ms_title"))
        author = clean_field(row.get("ms_author"))
        added_names = clean_field(row.get("ms_added_names"))
        date_place = clean_field(row.get("ms_date_place"))
        extent = clean_field(row.get("ms_extent"))
        notes = clean_field(row.get("ms_notes"))
        subjects = clean_field(row.get("ms_subjects"))
        script = clean_field(row.get("958$a")) or "Not Specified"
        colophon = clean_field(row.get("957$a"))
        shelfmark = clean_field(row.get("942$z")) or clean_field(row.get("090$a")) or "Shelfmark Not Recorded"
        library = clean_field(row.get("710$a")) or clean_field(row.get("942$a")) or "Library Unknown"
        library_city = clean_field(row.get("710$x"))
        place_writing = clean_field(row.get("751$a"))
        query_terms = [q.strip() for q in clean_field(row.get("query_terms")).split("|") if q.strip()]
        
        century = parse_century(date_place)
        year = extract_year(date_place)
        
        # Check local images
        has_images = mms_id in local_manuscript_dirs
        img_folder = ""
        img_list = []
        
        if has_images:
            folder_path = local_manuscript_dirs[mms_id]
            img_folder = folder_path.relative_to(PROJECT_ROOT).as_posix()
            # Load page info
            if mms_id in pages_by_mms:
                for p in pages_by_mms[mms_id]:
                    if not (folder_path / str(p.get("file_name"))).exists():
                        continue  # listed in the manifest but the download failed
                    img_list.append({
                        "file_name": p.get("file_name"),
                        "page_number": int(p.get("page_number", 1)),
                        "canvas_label": p.get("canvas_label", f"Page {p.get('page_number')}"),
                        "relative_path": f"{img_folder}/{p.get('file_name')}",
                        "width": p.get("width"),
                        "height": p.get("height")
                    })
            else:
                # Discover files directly in directory
                jpgs = sorted(folder_path.glob("*.jpg"))
                for i, jpg in enumerate(jpgs, 1):
                    img_list.append({
                        "file_name": jpg.name,
                        "page_number": i,
                        "canvas_label": f"Page {i}",
                        "relative_path": f"{img_folder}/{jpg.name}",
                        "width": None,
                        "height": None
                    })
                    
        ms_obj = {
            "mms_id": mms_id,
            "title": title,
            "author": author,
            "added_names": added_names,
            "shelfmark": shelfmark,
            "library": library,
            "library_city": library_city,
            "place_writing": place_writing,
            "date_place": date_place,
            "century": century,
            "year": year,
            # date range from step 1 (a century-only date covers the whole century), used by the map timeline
            "year_from": int(row["ms_year_from"]) if clean_field(row.get("ms_year_from")) else None,
            "year_to": int(row["ms_year_to"]) if clean_field(row.get("ms_year_to")) else None,
            "extent": extent,
            "script": script,
            "colophon": colophon,
            "notes": notes,
            "subjects": subjects,
            "query_terms": query_terms,
            "has_local_images": len(img_list) > 0,
            "image_folder": img_folder,
            "downloaded_pages_count": len(img_list),
            "pages": img_list,
            "manifest_url": f"https://iiif.nli.org.il/IIIFv21/{mms_id}/manifest",
            "ktiv_link": clean_field(row.get("ms_ktiv_link")),
            "parent_mms": clean_field(row.get("773$w")).split("|")[0].strip(),
            "added_titles": [t.strip() for t in clean_field(row.get("740$a")).split("|") if t.strip()],
            "contents": clean_field(row.get("505$a"))
        }
        
        manuscripts.append(ms_obj)
        
        # Aggregate Query Terms
        for q in query_terms:
            queries_map.setdefault(q, []).append(mms_id)
            
        # Aggregate Century
        century_map.setdefault(century, []).append(mms_id)
        
        # Aggregate Script
        for sc in script.split("|"):
            sc = sc.strip()
            if sc:
                script_map.setdefault(sc, []).append(mms_id)
                
        # Aggregate Persons (from author and added_names)
        raw_people = []
        if author:
            for a in author.split("|"):
                a = a.strip()
                if a and "PreferredLanguageHeading" not in a and a != "heb" and a != "lat":
                    raw_people.append((a, "Author"))
        if added_names:
            for an in added_names.split("|"):
                an = an.strip()
                if an and "PreferredLanguageHeading" not in an and an != "heb" and an != "lat":
                    role = "Associated Person / Owner"
                    if "מתרגם" in an or "translator" in an.lower():
                        role = "Translator"
                    elif "מעתיק" in an or "scribe" in an.lower():
                        role = "Scribe / Copyist"
                    elif "מפרש" in an or "commentator" in an.lower():
                        role = "Commentator"
                    raw_people.append((an, role))
                    
        for p_name, p_role in raw_people:
            # Clean name
            clean_name = re.sub(r'\b(מתרגם|מחבר|עורך|מעתיק|מפרש)\b', '', p_name).strip(' ,;')
            if len(clean_name) > 2:
                if clean_name not in persons_map:
                    persons_map[clean_name] = {
                        "name": clean_name,
                        "role": p_role,
                        "manuscripts": []
                    }
                persons_map[clean_name]["manuscripts"].append(mms_id)
                roles = persons_map[clean_name].setdefault("_roles", {})
                roles[p_role] = roles.get(p_role, 0) + 1
                
        # Aggregate Places of Writing
        if place_writing:
            for pw in place_writing.split("|"):
                pw = pw.strip()
                if pw:
                    places_writing_map.setdefault(pw, []).append(mms_id)
                    
        # Aggregate Library Cities
        if library_city:
            for lc in library_city.split("|"):
                lc = lc.strip()
                if lc:
                    places_holding_map.setdefault(lc, []).append(mms_id)

    # records with pages in Ktiv: from step 2's index (empty until step 2 has run)
    open_df = pd.DataFrame(columns=["mms_id", "canvases"])

    # Physical books: catalogue records that share a codex (same_codex_as) are counted once
    books_df = pd.DataFrame()
    index_csv = CSV_DIR / "MANUSCRIPTS_IMAGES_INDEX.csv"
    if index_csv.exists():
        books_df = pd.read_csv(index_csv, dtype=str).fillna("")
        if "status" in books_df.columns:   # step 2 checks every record live: count those with pages in Ktiv
            open_df = books_df[books_df["status"] != "no_pages_in_manifest"].rename(columns={"total_canvases": "canvases"})
        if "same_codex_as" in books_df.columns:
            books_df = books_df[books_df["same_codex_as"] == ""]
        if "status" in books_df.columns:
            books_df = books_df[books_df["status"] != "no_pages_in_manifest"]
    def book_pages(df, col):
        return int(pd.to_numeric(df[col], errors="coerce").sum()) if not df.empty else 0
    downloaded_books = books_df[books_df["status"] == "complete"] if "status" in books_df.columns else books_df

    # Format map locations with coordinates
    map_places = []
    
    # 1. Places of writing
    for place_name, ms_ids in places_writing_map.items():
        coord = None
        for k, v in COORDINATES.items():
            if k.lower() in place_name.lower() or place_name.lower() in k.lower():
                coord = v
                break
        if coord:
            map_places.append({
                "type": "writing",
                "name": place_name,
                "label": coord["label"],
                "lat": coord["lat"],
                "lon": coord["lon"],
                "count": len(ms_ids),
                "manuscripts": ms_ids
            })
            
    # 2. Holding library cities
    for city_name, ms_ids in places_holding_map.items():
        coord = None
        for k, v in COORDINATES.items():
            if k.lower() in city_name.lower() or city_name.lower() in k.lower():
                coord = v
                break
        if coord:
            map_places.append({
                "type": "holding",
                "name": city_name,
                "label": coord["label"],
                "lat": coord["lat"],
                "lon": coord["lon"],
                "count": len(ms_ids),
                "manuscripts": ms_ids
            })

    # Convert persons to sorted list by frequency
    sorted_persons = sorted(
        [v for v in persons_map.values() if len(v["manuscripts"]) >= 1],
        key=lambda x: len(x["manuscripts"]),
        reverse=True
    )
    for p in sorted_persons:
        p["count"] = len(p["manuscripts"])
        roles = p.pop("_roles")
        p["role"] = max(roles, key=roles.get)   # the role the person has in most records

    codices, texts = build_codices_and_texts(manuscripts, CSV_DIR / "MANUSCRIPTS_IMAGES_INDEX.csv")

    output_data = {
        "stats": {
            "physical_manuscripts": len(codices),
            "distinct_texts": len(texts),
            "total_manuscripts": len(manuscripts),
            "downloaded_manuscripts": len([m for m in manuscripts if m["has_local_images"]]),
            "total_downloaded_pages": sum(m["downloaded_pages_count"] for m in manuscripts),
            "total_open_in_catalog": int(open_df["mms_id"].nunique()),
            "total_pages_in_catalog": int(pd.to_numeric(open_df["canvases"], errors="coerce").sum()),
            "open_books": len(books_df),
            "open_book_pages": book_pages(books_df, "total_canvases"),
            "downloaded_books": len(downloaded_books),
            "downloaded_book_pages": book_pages(downloaded_books, "downloaded_pages")
        },
        "query_terms": {k: len(v) for k, v in queries_map.items()},
        "centuries": {k: len(v) for k, v in century_map.items()},
        "scripts": {k: len(v) for k, v in script_map.items()},
        "places": map_places,
        "persons": sorted_persons,
        "manuscripts": manuscripts,
        "codices": codices,
        "texts": texts
    }

    CLEAN_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Generated {OUTPUT_JSON.relative_to(PROJECT_ROOT)} ({OUTPUT_JSON.stat().st_size / 1024:.1f} KB)")
    print(f"  Total manuscripts: {len(manuscripts)}")
    print(f"  Manuscripts with images: {output_data['stats']['downloaded_manuscripts']}")
    print(f"  Pages indexed: {output_data['stats']['total_downloaded_pages']}")
    print(f"  Map locations: {len(map_places)}")
    print(f"  Persons indexed: {len(sorted_persons)}")
    print(f"  Physical manuscripts: {len(codices)} | distinct texts: {len(texts)}")


if __name__ == "__main__":
    build_data()
