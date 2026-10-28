#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP 5 - Find repeating illustrations by visual similarity.

Input:  data/illustrations/illustrations.csv (+ the crop files it points to)
Output: data/clusters/clusters.csv    one row per illustration: illustration_id, cluster_id, distance
        data/clusters/clusters.json   {"method": ..., "similarity_threshold": ...,
                                       "clusters": [{"cluster_id", "label", "n_manuscripts", "illustration_ids"}]}
No image files are copied: clusters refer to illustrations by illustration_id.

Goal: list the diagrams that repeat (within one manuscript or across several) and set apart the
ones that appear only once. There is no fixed number of groups; a similarity level decides.

How:
1. Each crop is turned into greyscale with stretched contrast and padded to a square on white.
   Without this, the models group mostly by paper tint and ink colour, i.e. by manuscript.
2. Two pretrained image models describe each crop as a list of numbers (an "embedding"):
   CLIP (openai/clip-vit-base-patch32), which captures what is depicted, and
   DINOv2 (facebook/dinov2-small), which captures shapes and layout.
   The similarity of two crops is the average of the two models' cosine similarities (1 = identical).
3. Complete-linkage agglomerative clustering joins crops into a group only if EVERY pair in the
   group is at least SIMILARITY_THRESHOLD similar. Groups therefore stay tight.
4. Crops left alone are put in group 0, "other (no close match)".

cluster_id 0       = other: no crop is similar enough. distance = 1 - similarity to its closest crop.
cluster_id 1..N    = repeating groups, largest first. distance = how far the crop is from the group's
                     centre (0 = most typical).
cluster_id N+1...  = Initials, Decorations and Tables: one fixed group per class, not compared (distance 0).

CorDeep false positives (microfilm target cards, the ruler) end up in their own small groups or in "other".

The earlier whole-page pHash attempt, which put 882 of 951 pages in single-page clusters,
is in git history, commit ce3442a.

Usage:  python code/05_cluster_illustrations.py
"""
import csv
import json
from typing import Dict, List

import numpy as np
import pandas as pd
import torch
from PIL import Image, ImageOps
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import normalize
from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor

from paths import PROJECT_ROOT, ILLUSTRATIONS_DIR, CLUSTERS_DIR

ILLUSTRATIONS_CSV = ILLUSTRATIONS_DIR / "illustrations.csv"
CLUSTERS_CSV = CLUSTERS_DIR / "clusters.csv"
CLUSTERS_JSON = CLUSTERS_DIR / "clusters.json"

CLIP_MODEL = "openai/clip-vit-base-patch32"
DINO_MODEL = "facebook/dinov2-small"
# Minimum similarity between every two crops in a group. Higher = stricter, fewer and tighter
# groups, more "other". Tried on the 124 diagrams: 0.78 -> 29 other, 0.82 -> 40, 0.86 -> 64.
SIMILARITY_THRESHOLD = 0.82
CLUSTERED_CLASS = "Content Illustration"
OTHER_ID = 0
METHOD = "greyscale CLIP ViT-B/32 + DINOv2-small embeddings, complete-linkage agglomerative"


def _prepare(path: str, size: int = 224) -> Image.Image:
    """Greyscale, stretch contrast, pad to a white square so the whole drawing stays in view."""
    im = ImageOps.autocontrast(Image.open(path).convert("L"), cutoff=2)
    w, h = im.size
    side = max(w, h)
    square = Image.new("L", (side, side), 255)
    square.paste(im, ((side - w) // 2, (side - h) // 2))
    return square.resize((size, size), Image.BICUBIC).convert("RGB")


def embed(crop_paths: List[str]) -> np.ndarray:
    """Return one vector per crop: CLIP and DINOv2 embeddings side by side.

    Rows are scaled so that the dot product of two rows is the average of the two models' cosine similarities.
    """
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    clip = CLIPModel.from_pretrained(CLIP_MODEL).to(device).eval()
    clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL)
    dino = AutoModel.from_pretrained(DINO_MODEL).to(device).eval()
    dino_processor = AutoImageProcessor.from_pretrained(DINO_MODEL)
    clip_features, dino_features = [], []
    with torch.no_grad():
        for start in range(0, len(crop_paths), 32):
            images = [_prepare(p) for p in crop_paths[start:start + 32]]
            pixels = clip_processor(images=images, return_tensors="pt")["pixel_values"].to(device)
            clip_features.append(clip.get_image_features(pixel_values=pixels).cpu().numpy())
            pixels = dino_processor(images=images, return_tensors="pt", do_resize=False,
                                    do_center_crop=False)["pixel_values"].to(device)
            tokens = dino(pixel_values=pixels).last_hidden_state
            # class token + average of the patch tokens
            dino_features.append(torch.cat([tokens[:, 0], tokens[:, 1:].mean(1)], 1).cpu().numpy())
    both = np.hstack([normalize(np.concatenate(clip_features)), normalize(np.concatenate(dino_features))])
    return both / np.sqrt(2)


def cluster(features: np.ndarray) -> List[Dict]:
    """Return [{'cluster_id': int, 'distance': float}, ...] in the same order as features.

    Crops with no partner above SIMILARITY_THRESHOLD get OTHER_ID; groups are numbered 1.. by size.
    """
    labels = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="complete",
                                     distance_threshold=1 - SIMILARITY_THRESHOLD).fit_predict(features)
    groups = [c for c in set(labels) if (labels == c).sum() > 1]
    groups.sort(key=lambda c: -(labels == c).sum())
    new_id = {old: new for new, old in enumerate(groups, start=1)}

    similarity = features @ features.T
    np.fill_diagonal(similarity, -1)
    distances = 1 - similarity.max(axis=1)                 # for "other": distance to closest crop
    for c in groups:
        members = labels == c
        centre = normalize(features[members].mean(axis=0, keepdims=True))[0]
        distances[members] = 1 - normalize(features[members]) @ centre
    return [{"cluster_id": new_id.get(l, OTHER_ID), "distance": round(float(d), 4)}
            for l, d in zip(labels, distances)]


def main():
    ill = pd.read_csv(ILLUSTRATIONS_CSV, dtype=str)
    is_diagram = ill["class"] == CLUSTERED_CLASS
    diagrams = ill[is_diagram]
    features = embed([str(PROJECT_ROOT / p) for p in diagrams["crop_file"]])
    assignments = dict(zip(diagrams["illustration_id"], cluster(features)))
    n_groups = max(a["cluster_id"] for a in assignments.values())
    labels = {OTHER_ID: "other (no close match)"}
    labels.update({i: f"repeating group {i}" for i in range(1, n_groups + 1)})

    # every other class gets one fixed group, numbered after the diagram groups
    for n, cls in enumerate(sorted(ill.loc[~is_diagram, "class"].unique()), start=n_groups + 1):
        labels[n] = f"{cls} (not compared)"
        for iid in ill.loc[ill["class"] == cls, "illustration_id"]:
            assignments[iid] = {"cluster_id": n, "distance": 0.0}

    rows = [{"illustration_id": iid, **assignments[iid]} for iid in ill["illustration_id"]]
    CLUSTERS_DIR.mkdir(parents=True, exist_ok=True)
    with CLUSTERS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["illustration_id", "cluster_id", "distance"])
        w.writeheader()
        w.writerows(rows)

    manuscript = dict(zip(ill["illustration_id"], ill["manuscript_folder"]))
    groups: Dict[int, List[str]] = {}
    for r in rows:
        groups.setdefault(r["cluster_id"], []).append(r["illustration_id"])
    with CLUSTERS_JSON.open("w", encoding="utf-8") as f:
        json.dump({"method": METHOD,
                   "similarity_threshold": SIMILARITY_THRESHOLD,
                   "clusters": [{"cluster_id": k, "label": labels[k],
                                 "n_manuscripts": len({manuscript[i] for i in v}),
                                 "illustration_ids": v}
                                for k, v in sorted(groups.items())]},
                  f, ensure_ascii=False, indent=2)
    n_other = len(groups.get(OTHER_ID, []))
    n_cross = sum(1 for k in range(1, n_groups + 1) if len({manuscript[i] for i in groups[k]}) > 1)
    print(f"{len(diagrams)} diagrams: {n_groups} repeating groups ({n_cross} spanning several manuscripts), "
          f"{n_other} other; {len(rows)} illustrations in total -> {CLUSTERS_DIR.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
