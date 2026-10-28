# -*- coding: utf-8 -*-
"""
Shared folder locations for every pipeline step.

code/01_scrape_metadata.py        -> data/metadata/raw/
code/02_download_manuscripts.py   -> data/manuscripts/   (+ index CSVs in data/metadata/raw/)
code/03_organize_metadata.py      -> data/metadata/clean/
code/04_extract_illustrations.py  -> data/illustrations/
code/05_cluster_illustrations.py  -> data/clusters/
code/06_build_visualizer.py       -> visualizer/
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = PROJECT_ROOT / "code"
DATA_DIR = PROJECT_ROOT / "data"

# 1. metadata
METADATA_DIR = DATA_DIR / "metadata"
RAW_METADATA_DIR = METADATA_DIR / "raw"            # harvest + download CSVs, as produced
MARCXML_DIR = RAW_METADATA_DIR / "marcxml"         # one MARCXML collection per search term
CLEAN_METADATA_DIR = METADATA_DIR / "clean"        # tidied metadata used by the visualizer

# 2. digitized manuscripts: data/manuscripts/<mms_id>_<library>_<shelfmark>/NNNN.jpg + metadata.json
MANUSCRIPTS_DIR = DATA_DIR / "manuscripts"

# 3. extracted illustrations: data/illustrations/<manuscript folder>/<crop>.png + illustrations.csv
ILLUSTRATIONS_DIR = DATA_DIR / "illustrations"

# 4. clustering results (data only, no image copies)
CLUSTERS_DIR = DATA_DIR / "clusters"

# visualizer: template sources in code/, built site in visualizer/
VISUALIZER_TEMPLATE_DIR = CODE_DIR / "visualizer_template"
VISUALIZER_DIR = PROJECT_ROOT / "visualizer"
