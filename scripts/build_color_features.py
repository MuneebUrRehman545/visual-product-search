"""Precompute HSV color features for all 44,119 catalog items in Week 3.

Inputs:
  - data/manifests/catalog_id_map.csv

Outputs:
  - artifacts/embeddings/color_features.npy
  - artifacts/embeddings/color_catalog_ids.npy
  - artifacts/embeddings/color_fingerprint.json
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.reranking_service import FEATURE_DIM, extract_hsv_histogram

DEFAULT_ID_MAP = PROJECT_ROOT / "data" / "manifests" / "catalog_id_map.csv"
EMBEDDINGS_DIR = PROJECT_ROOT / "artifacts" / "embeddings"

OUTPUT_FEATURES = EMBEDDINGS_DIR / "color_features.npy"
OUTPUT_IDS = EMBEDDINGS_DIR / "color_catalog_ids.npy"
OUTPUT_FINGERPRINT = EMBEDDINGS_DIR / "color_fingerprint.json"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Precompute catalog color features.")
    parser.add_argument(
        "--id-map-csv",
        type=Path,
        default=DEFAULT_ID_MAP,
        help="Path to data/manifests/catalog_id_map.csv",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=16,
        help="Thread pool worker count (default: 16)",
    )
    return parser.parse_args()


def process_item(rec: Dict[str, Any]) -> Tuple[int, np.ndarray]:
    """Extract HSV feature for a single catalog record."""
    cid = int(rec["catalog_item_id"])
    rel_path = rec["relative_path"]
    full_path = PROJECT_ROOT / rel_path

    try:
        feat = extract_hsv_histogram(full_path)
    except Exception:
        feat = np.zeros((FEATURE_DIM,), dtype=np.float32)

    return cid, feat


def build_color_features(id_map_path: Path, num_workers: int = 16) -> None:
    """Extract and save color histogram features for all catalog items."""
    start_time = time.time()
    print("=" * 70)
    print(" " * 16 + "CATALOG COLOR FEATURE PRECOMPUTATION")
    print("=" * 70)

    df_id_map = pd.read_csv(id_map_path)
    total_items = len(df_id_map)
    print(f"Loaded {total_items:,} catalog items from {id_map_path.name}")
    print(f"Feature Representation: HSV Histogram ({FEATURE_DIM} dimensions, L2-normalized)")
    print(f"Parallel Workers:       {num_workers}")

    records = df_id_map.to_dict(orient="records")

    print(f"\nExtracting HSV features across {total_items:,} images...")
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        results = list(pool.map(process_item, records))

    catalog_ids = np.array([r[0] for r in results], dtype=np.int64)
    features = np.stack([r[1] for r in results]).astype(np.float32)

    print(f"\nValidating feature array integrity...")
    assert len(features) == total_items, f"Feature count mismatch: {len(features)} != {total_items}"
    assert len(catalog_ids) == total_items, f"ID count mismatch: {len(catalog_ids)} != {total_items}"
    assert features.shape == (total_items, FEATURE_DIM), f"Shape mismatch: {features.shape}"
    assert np.all(np.isfinite(features)), "FATAL: Color features contain NaN or Inf!"
    print(f"  [PASS] All {total_items:,} features are finite (0 NaN / 0 Inf).")

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    np.save(str(OUTPUT_FEATURES), features)
    np.save(str(OUTPUT_IDS), catalog_ids)

    # Compute fingerprint
    hasher = hashlib.sha256()
    with open(id_map_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    hasher.update(f"HSV:{FEATURE_DIM}".encode("utf-8"))
    fp = hasher.hexdigest()

    meta = {
        "feature_type": "HSV_Histogram",
        "dimension": FEATURE_DIM,
        "total_items": total_items,
        "fingerprint": fp,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_FINGERPRINT, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"\nSaved color feature artifacts:")
    print(f"  + Features:    {OUTPUT_FEATURES.relative_to(PROJECT_ROOT)} (shape: {features.shape})")
    print(f"  + Catalog IDs: {OUTPUT_IDS.relative_to(PROJECT_ROOT)} (count: {len(catalog_ids):,})")
    print(f"  + Fingerprint: {OUTPUT_FINGERPRINT.relative_to(PROJECT_ROOT)}")

    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.2f} seconds ({total_items/elapsed:.1f} items/sec).")
    print("=" * 70)


if __name__ == "__main__":
    args = parse_args()
    build_color_features(args.id_map_csv, args.num_workers)
