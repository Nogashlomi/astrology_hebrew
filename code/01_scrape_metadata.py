# -*- coding: utf-8 -*-
"""
STEP 1 - Scrape manuscript metadata from Ktiv / the NLI Alma catalogue (SRU) and choose the corpus:
Hebrew manuscripts tagged "astrology", dated 1250-1450.

Outputs:
  data/metadata/raw/marcxml/<query>__marcxml.xml  raw MARCXML per search
  data/metadata/raw/ALL__deduped.csv              every record found, one row per MMS ID, with the filter columns
  data/metadata/raw/MANUSCRIPTS_ONLY.csv          the corpus: records that pass every filter (read by steps 2 and 3)
  data/metadata/raw/_SUMMARY.csv                  counts per search, and how many records each filter removed

How Ktiv tags astrology (checked on sample records, October 2026):
  650 $a "Astrology" (Latin-script heading; the catalogue also indexes it under the Hebrew "אסטרולוגיה"), and
  Ktiv's own subject notes in 500 $a, e.g. "נושא נוסף: מדעים. אסטרולוגיה".
The searches below find every manuscript record that mentions the word; a record is kept only when the word
is in one of these subject fields (not just somewhere in a free-text note).

Filters, in order (each record gets a yes/no column for each):
  1. manuscript      - MARC Leader position 06 is t, d or f (manuscript text, music, map)
  2. astrology tag   - 650/651/655/690 subject heading, a Ktiv "נושא נוסף" note, or the title (245/246)
                       contains astrolog-/אסטרולוג-. A word found only in free-text notes (500/505) or in
                       the parent volume's title (773) does not count.
  3. Hebrew          - language (008/35-37) is Hebrew or a Jewish language written in Hebrew script
                       (Judeo-Arabic, Ladino, Judeo-Persian, Yiddish, Aramaic), or the record names a
                       Hebrew script type (958 $a, e.g. "ספרדית"), which Ktiv records only for Hebrew script
  4. date 1250-1450  - see date_range() below: kept when the record's date range overlaps 1250-1450
"""
import csv
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import requests
import xml.etree.ElementTree as ET

from paths import MARCXML_DIR, RAW_METADATA_DIR

# ---------------------------------------------------------------
# 1. Settings (same SRU address as in the example – it works)
# ---------------------------------------------------------------
ALMA_DOMAIN = "nli.alma.exlibrisgroup.com"
INSTITUTION_CODE = "972NNL_INST"
BASE_SRU = f"https://{ALMA_DOMAIN}/view/sru/{INSTITUTION_CODE}"

# Searches (CQL). type_of_record="t" = manuscripts, so the server does the first filter for us.
# The Hebrew and English words find almost the same records; together they also catch records
# that use only one of the two languages.
# Each search has a short label, shown in the visualizer's "Search Queries" tab.
QUERIES = [
    ("אסטרולוגיה (any field)", 'alma.all_for_ui all "אסטרולוגיה" and alma.type_of_record="t"'),
    ("Astrology (any field)", 'alma.all_for_ui all "Astrology" and alma.type_of_record="t"'),
    ("Astrology (subject heading)", 'alma.subjects all "Astrology" and alma.type_of_record="t"'),
]

YEAR_FROM, YEAR_TO = 1250, 1450
HEBREW_SCRIPT_LANGUAGES = {"heb", "jrb", "lad", "jpr", "yid", "arc", "jdt", "sam"}

MARC_NS = {"marc": "http://www.loc.gov/MARC21/slim"}
SRU_NS = {"sru": "http://www.loc.gov/zing/srw/"}
MAX_PER_REQUEST = 50
SLEEP_S = 0.5   # a bit slower than the example, to be gentle with the server

RAW_DIR = MARCXML_DIR
CSV_DIR = RAW_METADATA_DIR


# ---------------------------------------------------------------
# 2. SRU helpers (from the example)
# ---------------------------------------------------------------
def sru_search(cql: str, start: int, max_records: int) -> str:
    params = {"version": "1.2", "operation": "searchRetrieve", "query": cql,
              "recordSchema": "marcxml", "startRecord": str(start),
              "maximumRecords": str(max_records)}
    for attempt in range(1, 6):   # the server sometimes drops a connection; wait and try again
        try:
            r = requests.get(BASE_SRU, params=params, timeout=120)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt == 5:
                raise
            print(f"  SRU request failed ({type(e).__name__}), retrying in {10 * attempt}s")
            time.sleep(10 * attempt)


def parse_total(xml_text: str) -> int:
    n = ET.fromstring(xml_text).find(".//sru:numberOfRecords", SRU_NS)
    return int(n.text) if n is not None and n.text else 0


def extract_marc_records(xml_text: str) -> List[ET.Element]:
    return ET.fromstring(xml_text).findall(".//marc:record", MARC_NS)


def harvest(cql: str) -> Tuple[str, int, List[ET.Element]]:
    first = sru_search(cql, 1, MAX_PER_REQUEST)
    total = parse_total(first)
    records = extract_marc_records(first)
    start = 1 + len(records)
    while len(records) < total:
        batch = extract_marc_records(sru_search(cql, start, MAX_PER_REQUEST))
        if not batch:
            break
        records.extend(batch)
        start += len(batch)
        time.sleep(SLEEP_S)
    return cql, total, records


# ---------------------------------------------------------------
# 3. MARC helpers
# ---------------------------------------------------------------
def control(rec: ET.Element, tag: str) -> str:
    cf = rec.find(f"marc:controlfield[@tag='{tag}']", MARC_NS)
    return (cf.text or "").strip() if cf is not None else ""


def leader(rec: ET.Element) -> str:
    ld = rec.find("marc:leader", MARC_NS)
    return ld.text if ld is not None and ld.text else ""


def is_manuscript(rec: ET.Element) -> bool:
    """
    MARC Leader position 06 = type of record.
    t = manuscript language material, d = manuscript music, f = manuscript map.
    To check on the first run: do all the Ktiv records really have 't'?
    """
    ld = leader(rec)
    return len(ld) > 6 and ld[6] in "tdf"


def subfields(df: ET.Element, codes: str = None) -> List[str]:
    out = []
    for sf in df.findall("marc:subfield", MARC_NS):
        if codes is None or sf.attrib.get("code") in codes:
            v = (sf.text or "").strip()
            if v:
                out.append(v)
    return out


def field_text(rec: ET.Element, tag: str, codes: str = None, sep: str = " ") -> List[str]:
    return [sep.join(subfields(df, codes)) for df in rec.findall(f"marc:datafield[@tag='{tag}']", MARC_NS)]



ASTRO_RE = re.compile(r"astrolog|אסטרולוג", re.I)


def astrology_tag(rec: ET.Element) -> str:
    """Where the record is tagged astrology, or '' if it is not: '650' (or 651/655/690) = subject heading,
    'note' = Ktiv 'נושא נוסף' subject note, 'title' = the work's own title (245/246), e.g. 'קובץ באסטרולוגיה'."""
    for tag in ("650", "651", "655", "690"):
        if any(ASTRO_RE.search(t) for t in field_text(rec, tag, "axyzv")):
            return tag
    if any(t.startswith("נושא נוסף") and ASTRO_RE.search(t) for t in field_text(rec, "500", "a")):
        return "note"
    if any(ASTRO_RE.search(t) for t in field_text(rec, "245", "abnp") + field_text(rec, "246", "abnp")):
        return "title"
    return ""


def is_hebrew(rec: ET.Element) -> bool:
    lang = control(rec, "008")[35:38]
    return lang in HEBREW_SCRIPT_LANGUAGES or bool(field_text(rec, "958", "a"))


# Hebrew numerals: century numbers such as י"ג (13), י"ד (14), ט"ו (15)
GEMATRIA = dict(zip("אבגדהוזחטיכלמנסעפצקרשת", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90,
                                                100, 200, 300, 400]))
GEMATRIA.update({"ך": 20, "ם": 40, "ן": 50, "ף": 80, "ץ": 90})
HEB_NUMBER = r"[א-ת]{1,2}[\"״'׳][א-ת]?"
# part of a century -> (first, last) year within it
CENTURY_PARTS = [
    (r"מחצית\s+(ה)?ראשונה|מחצית\s+א", (0, 50)), (r"מחצית\s+(ה)?שני(י)?ה|מחצית\s+ב", (50, 99)),
    (r"רבע\s+(ה)?ראשון", (0, 25)), (r"רבע\s+(ה)?אחרון", (75, 99)),
    (r"first half", (0, 50)), (r"תחילת|ראשית|early|beginning", (0, 33)), (r"אמצע|middle|mid", (33, 67)),
    (r"סוף|שלהי|late|end", (67, 99)), (r"second half", (50, 99)),
]


def hebrew_number(token: str) -> int:
    return sum(GEMATRIA.get(c, 0) for c in token)


def century_range(text: str) -> Optional[Tuple[int, int]]:
    """'מאה י"ד' -> (1300, 1399); 'סוף מאה ט"ו' -> (1467, 1499); 'מאות י"ד-ט"ו' -> (1300, 1499).
    Also '15th century'. A part-of-century word (תחילת, אמצע, סוף, מחצית ...) just before a number narrows it."""
    lows, highs = [], []
    if re.search(r"מא(ה|ות)", text):
        for m in re.finditer(HEB_NUMBER, text):
            n = hebrew_number(m.group())
            if 9 <= n <= 21:
                part = century_part(text[max(0, m.start() - 25):m.start()])
                lows.append((n - 1) * 100 + part[0])
                highs.append((n - 1) * 100 + part[1])
    for m in re.finditer(r"(\d{1,2})(st|nd|rd|th)\s*(-\s*\d{1,2}(st|nd|rd|th)\s*)?cent", text, re.I):
        part = century_part(text[max(0, m.start() - 20):m.start()])
        n = int(m.group(1))
        lows.append((n - 1) * 100 + part[0])
        n2 = int(re.search(r"\d+", m.group(3)).group()) if m.group(3) else n
        highs.append((n2 - 1) * 100 + part[1])
    return (min(lows), max(highs)) if lows else None


def century_part(before: str) -> Tuple[int, int]:
    """The part of the century named just before a century number (whole century if none)."""
    after_dash = re.split(r"[-–]", before)[-1]      # in 'סוף מאה י"ד-ט"ו' the 'סוף' belongs to י"ד only
    for pattern, part in CENTURY_PARTS:
        if re.search(pattern, after_dash, re.I):
            return part
    return (0, 99)


def date_range(rec: ET.Element) -> Tuple[Optional[int], Optional[int], str]:
    """(first year, last year, source) of the record's date.

    1. Gregorian years written in 260/264 $c, e.g. 'ה'קנ"ב (1392)' or '[1380-1400]'.
    2. Centuries written in 260/264 $c, e.g. 'מאה י"ד', 'סוף מאה ט"ו', '14th century'.
    3. MARC 008 positions 07-14 (date 1, date 2): 'u' marks an unknown digit, so '14uu' = 1400-1499.
       At least the century must be known: '1uuu' (some time 1000-1999) counts as undated.
    """
    text = " ".join(field_text(rec, "260", "c") + field_text(rec, "264", "c"))
    years = [int(y) for y in re.findall(r"(?<!\d)(1[0-9]{3})(?!\d)", text) if 900 <= int(y) <= 1950]
    if years:
        return min(years), max(years), "260/264 year"
    cent = century_range(text)
    if cent:
        return cent[0], cent[1], "260/264 century"
    f008 = control(rec, "008")
    d1, d2 = f008[7:11], f008[11:15]
    if re.fullmatch(r"\d\d[\du]{2}", d1):
        low, high = int(d1.replace("u", "0")), int(d1.replace("u", "9"))
        if re.fullmatch(r"\d[\du]{3}", d2) and f008[6:7] in "qmik":
            high = max(high, int(d2.replace("u", "9")))
        return low, high, "008"
    return None, None, ""


def marc_to_flat_dict(rec: ET.Element) -> Dict[str, str]:
    """
    (a) every MARC field as its own column: '245$a', '500$a', ... (as in the example)
    (b) a few readable 'ms_*' columns.
    """
    out: Dict[str, List[str]] = {}
    out["LDR"] = [leader(rec)]
    for cf in rec.findall("marc:controlfield", MARC_NS):
        out.setdefault(cf.attrib.get("tag", ""), []).append((cf.text or "").strip())
    for df in rec.findall("marc:datafield", MARC_NS):
        tag = df.attrib.get("tag")
        for sf in df.findall("marc:subfield", MARC_NS):
            code = sf.attrib.get("code")
            if tag and code:
                out.setdefault(f"{tag}${code}", []).append((sf.text or "").strip())
    flat = {k: " | ".join(v) for k, v in out.items()}

    mms = control(rec, "001")
    flat["ms_mms_id"] = mms
    flat["ms_is_manuscript"] = "yes" if is_manuscript(rec) else "no"
    flat["ms_title"] = " | ".join(field_text(rec, "245", "abnp"))
    flat["ms_author"] = " | ".join(field_text(rec, "100", "aqde"))
    flat["ms_added_names"] = " | ".join(field_text(rec, "700", "aqdet"))
    flat["ms_date_place"] = " | ".join(field_text(rec, "260") + field_text(rec, "264"))
    flat["ms_extent"] = " | ".join(field_text(rec, "300"))
    flat["ms_notes"] = " || ".join(field_text(rec, "500", "a"))
    flat["ms_subjects"] = " | ".join(field_text(rec, "650", "axyzv", " -- "))
    tag = astrology_tag(rec)
    year_from, year_to, date_source = date_range(rec)
    in_period = year_from is not None and year_from <= YEAR_TO and year_to >= YEAR_FROM
    flat["ms_astrology_tag"] = tag
    flat["ms_hebrew"] = "yes" if is_hebrew(rec) else "no"
    flat["ms_year_from"] = "" if year_from is None else str(year_from)
    flat["ms_year_to"] = "" if year_to is None else str(year_to)
    flat["ms_date_source"] = date_source
    flat["ms_in_period"] = "yes" if in_period else "no"
    flat["ms_selected"] = "yes" if (flat["ms_is_manuscript"] == "yes" and tag and flat["ms_hebrew"] == "yes"
                                    and in_period) else "no"
    flat["ms_ktiv_link"] = ("https://www.nli.org.il/he/discover/manuscripts/hebrew-manuscripts/"
                            f"viewerpage?vid=MANUSCRIPTS&docid=PNX_MANUSCRIPTS{mms}") if mms else ""
    flat["ms_iiif_manifest"] = f"https://iiif.nli.org.il/IIIFv21/{mms}/manifest" if mms else ""
    return flat


# ---------------------------------------------------------------
# 4. Output (from the example)
# ---------------------------------------------------------------
def write_csv(rows: List[Dict[str, str]], path: Path) -> None:
    # put the readable columns first, then the raw MARC columns
    keys = sorted({k for r in rows for k in r})
    first = [k for k in keys if k.startswith("ms_") or k.startswith("query")]
    fieldnames = first + [k for k in keys if k not in first]
    with path.open("w", encoding="utf-8-sig", newline="") as f:   # utf-8-sig = Hebrew opens well in Excel
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_marcxml_collection(records: List[ET.Element], path: Path) -> None:
    root = ET.Element("collection", xmlns=MARC_NS["marc"])
    for r in records:
        root.append(r)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------
# 5. Main harvest
# ---------------------------------------------------------------
def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    combined, summary, seen = [], [], {}
    for n, (term, cql) in enumerate(QUERIES, 1):
        print(f"\nHarvesting: {term}: {cql}")
        cql, total, recs = harvest(cql)
        safe = f"{n:02d}_" + re.sub(r"\W+", "_", term).strip("_")
        write_marcxml_collection(recs, RAW_DIR / f"{safe}__marcxml.xml")
        n_ms = 0
        for rec in recs:
            row = marc_to_flat_dict(rec)
            n_ms += row["ms_is_manuscript"] == "yes"
            mms = row["ms_mms_id"]
            if mms in seen:                      # same record found by another query
                seen[mms]["query_terms"] += " | " + term
                continue
            row["query_terms"] = term
            seen[mms] = row
            combined.append(row)
        summary.append({"term": term, "cql": cql, "reported_total": total,
                        "downloaded": len(recs), "manuscripts": n_ms})
        print(f"  total: {total}  downloaded: {len(recs)}  manuscripts: {n_ms}")
        time.sleep(SLEEP_S)

    # how many records each filter removes, in order
    left = combined
    for name, keep in [("manuscript (Leader/06)", lambda r: r["ms_is_manuscript"] == "yes"),
                       ("tagged astrology (subject heading, Ktiv subject note or title)", lambda r: r["ms_astrology_tag"]),
                       ("Hebrew script", lambda r: r["ms_hebrew"] == "yes"),
                       (f"dated within {YEAR_FROM}-{YEAR_TO}", lambda r: r["ms_in_period"] == "yes")]:
        kept = [r for r in left if keep(r)]
        summary.append({"term": f"filter: {name}", "cql": "", "reported_total": len(left),
                        "downloaded": len(kept), "manuscripts": len(left) - len(kept)})
        print(f"  {name}: {len(left)} -> {len(kept)}")
        left = kept

    write_csv(combined, CSV_DIR / "ALL__deduped.csv")
    write_csv([r for r in combined if r["ms_selected"] == "yes"], CSV_DIR / "MANUSCRIPTS_ONLY.csv")
    write_csv(summary, CSV_DIR / "_SUMMARY.csv")
    print(f"\nDone. {len(combined)} unique records, {len(left)} in the corpus (MANUSCRIPTS_ONLY.csv); "
          f"MARCXML in {RAW_DIR}, CSV in {CSV_DIR}")


if __name__ == "__main__":
    main()
