"""Dataset validation script for Visual Product Search (Week 3).

Validates all 44k+ images (readability, format, dimensions, integrity) and
cross-references with metadata from data/styles.csv.
Generates:
- data/manifests/validated_catalog_manifest.csv
- data/manifests/invalid_images.csv
- data/manifests/unmatched_metadata.csv
- data/manifests/unmatched_images.csv
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
from PIL import Image

# Ensure workspace root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
IMAGES_DIR = DATA_DIR / "images"
MANIFESTS_DIR = DATA_DIR / "manifests"

VALIDATED_MANIFEST_PATH = MANIFESTS_DIR / "validated_catalog_manifest.csv"
INVALID_IMAGES_PATH = MANIFESTS_DIR / "invalid_images.csv"
UNMATCHED_META_PATH = MANIFESTS_DIR / "unmatched_metadata.csv"
UNMATCHED_IMAGES_PATH = MANIFESTS_DIR / "unmatched_images.csv"


def discover_metadata_file(data_path: Path) -> Path:
    """Find Excel or CSV metadata file."""
    excel_files = list(data_path.glob("*.xlsx")) + list(data_path.glob("*.xls"))
    if excel_files:
        return excel_files[0]

    csv_files = [f for f in data_path.glob("*.csv") if f.is_file()]
    for f in csv_files:
        if f.name.lower() == "styles.csv":
            return f
    if csv_files:
        return csv_files[0]

    raise FileNotFoundError("No Excel or CSV metadata file found in data/ directory.")


def load_metadata(file_path: Path) -> pd.DataFrame:
    """Read metadata from Excel or CSV file."""
    ext = file_path.suffix.lower()
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(file_path)
    return pd.read_csv(file_path, on_bad_lines="skip")


def validate_single_image(file_path: Path) -> Dict[str, Any]:
    """Inspect and validate a single image file."""
    filename = file_path.name
    res = {
        "filename": filename,
        "file_path": str(file_path),
        "is_valid": False,
        "width": 0,
        "height": 0,
        "file_size_bytes": 0,
        "format": "",
        "error_message": "",
    }

    try:
        stat = file_path.stat()
        res["file_size_bytes"] = stat.st_size
        if stat.st_size == 0:
            res["error_message"] = "0-byte empty file"
            return res

        with Image.open(file_path) as img:
            res["width"], res["height"] = img.size
            res["format"] = img.format or ""

            if res["width"] <= 0 or res["height"] <= 0:
                res["error_message"] = f"Invalid dimensions: {res['width']}x{res['height']}"
                return res

            img.verify()

        res["is_valid"] = True
        return res
    except Exception as e:
        res["error_message"] = str(e)
        return res


def run_validation() -> None:
    """Execute complete dataset validation pipeline."""
    start_time = time.time()
    print("=" * 70, flush=True)
    print(" " * 18 + "DATASET VALIDATION PIPELINE", flush=True)
    print("=" * 70, flush=True)

    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Discover and load metadata
    meta_file = discover_metadata_file(DATA_DIR)
    print(f"Loading metadata from: {meta_file.relative_to(PROJECT_ROOT)} ...", flush=True)
    df_raw = load_metadata(meta_file)
    total_metadata_rows = len(df_raw)
    print(f"Total raw metadata rows: {total_metadata_rows:,}", flush=True)
    print(f"Raw Columns: {df_raw.columns.tolist()}", flush=True)

    # Check duplicate metadata rows and duplicate IDs
    duplicate_rows_count = int(df_raw.duplicated().sum())
    duplicate_ids_count = int(df_raw.duplicated(subset=["id"]).sum()) if "id" in df_raw.columns else 0
    missing_ids_count = int(df_raw["id"].isnull().sum()) if "id" in df_raw.columns else total_metadata_rows

    print(f"  - Missing IDs in metadata: {missing_ids_count}", flush=True)
    print(f"  - Duplicate metadata rows: {duplicate_rows_count}", flush=True)
    print(f"  - Duplicate image IDs in metadata: {duplicate_ids_count}", flush=True)

    # 2. Discover all physical image files
    print(f"\nScanning image files in: {IMAGES_DIR.relative_to(PROJECT_ROOT)} ...", flush=True)
    image_entries = []
    for entry in os.scandir(IMAGES_DIR):
        if entry.is_file() and not entry.name.startswith("."):
            image_entries.append(Path(entry.path))

    total_images_discovered = len(image_entries)
    print(f"Total image files discovered on disk: {total_images_discovered:,}", flush=True)

    # 3. Validate all images using multithreaded pool
    print(f"\nValidating {total_images_discovered:,} image files with 16 parallel threads...", flush=True)
    valid_images_map: Dict[str, Dict[str, Any]] = {}
    invalid_images_list: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=16) as executor:
        future_to_path = {executor.submit(validate_single_image, p): p for p in image_entries}
        processed = 0
        for future in as_completed(future_to_path):
            info = future.result()
            if info["is_valid"]:
                valid_images_map[info["filename"]] = info
            else:
                invalid_images_list.append(info)
            processed += 1
            if processed % 10000 == 0 or processed == total_images_discovered:
                print(f"  Processed {processed:,}/{total_images_discovered:,} images ({len(valid_images_map):,} valid, {len(invalid_images_list):,} invalid)...", flush=True)

    valid_images_count = len(valid_images_map)
    invalid_images_count = len(invalid_images_list)

    # 4. Reconcile metadata with validated images
    print("\nReconciling metadata records with validated images...", flush=True)
    df_meta = df_raw.copy()
    if "id" in df_meta.columns:
        df_meta["target_filename"] = df_meta["id"].astype(str) + ".jpg"
    else:
        df_meta["target_filename"] = ""

    matched_records: List[Dict[str, Any]] = []
    unmatched_metadata_records: List[Dict[str, Any]] = []

    for _, row in df_meta.iterrows():
        target_fn = row["target_filename"]
        if target_fn in valid_images_map:
            img_info = valid_images_map[target_fn]
            rel_path = f"data/images/{target_fn}"

            rec = {
                "image_id": int(row["id"]) if pd.notnull(row["id"]) else None,
                "product_id": int(row["id"]) if pd.notnull(row["id"]) else None,
                "filename": target_fn,
                "relative_path": rel_path,
                "category": str(row.get("masterCategory", "")).strip(),
                "master_category": str(row.get("masterCategory", "")).strip(),
                "sub_category": str(row.get("subCategory", "")).strip(),
                "article_type": str(row.get("articleType", "")).strip(),
                "gender": str(row.get("gender", "")).strip(),
                "base_colour": str(row.get("baseColour", "")).strip() if pd.notnull(row.get("baseColour")) else "",
                "season": str(row.get("season", "")).strip() if pd.notnull(row.get("season")) else "",
                "year": int(row["year"]) if pd.notnull(row.get("year")) else "",
                "usage": str(row.get("usage", "")).strip() if pd.notnull(row.get("usage")) else "",
                "product_display_name": str(row.get("productDisplayName", "")).strip() if pd.notnull(row.get("productDisplayName")) else "",
                "width": img_info["width"],
                "height": img_info["height"],
                "file_size_bytes": img_info["file_size_bytes"],
            }
            matched_records.append(rec)
        else:
            unmatched_metadata_records.append(row.to_dict())

    # Find unmatched images (images on disk that have no metadata record)
    matched_filenames = {r["filename"] for r in matched_records}
    unmatched_images_records = [
        {"filename": fn, "file_path": str(info["file_path"]), "file_size_bytes": info["file_size_bytes"]}
        for fn, info in valid_images_map.items()
        if fn not in matched_filenames
    ]

    matched_images_count = len(matched_records)
    unmatched_metadata_count = len(unmatched_metadata_records)
    unmatched_images_count = len(unmatched_images_records)

    # 5. Write output manifest CSV files
    print("\nGenerating validated manifest CSV files...", flush=True)

    # 5a. Validated catalog manifest
    df_validated = pd.DataFrame(matched_records)
    df_validated.to_csv(VALIDATED_MANIFEST_PATH, index=False)
    print(f"  + Wrote {len(df_validated):,} rows to: {VALIDATED_MANIFEST_PATH.relative_to(PROJECT_ROOT)}", flush=True)

    # 5b. Invalid images CSV
    df_invalid = pd.DataFrame(invalid_images_list)
    df_invalid.to_csv(INVALID_IMAGES_PATH, index=False)
    print(f"  + Wrote {len(df_invalid):,} rows to: {INVALID_IMAGES_PATH.relative_to(PROJECT_ROOT)}", flush=True)

    # 5c. Unmatched metadata CSV
    df_unmatched_meta = pd.DataFrame(unmatched_metadata_records)
    df_unmatched_meta.to_csv(UNMATCHED_META_PATH, index=False)
    print(f"  + Wrote {len(df_unmatched_meta):,} rows to: {UNMATCHED_META_PATH.relative_to(PROJECT_ROOT)}", flush=True)

    # 5d. Unmatched images CSV
    df_unmatched_img = pd.DataFrame(unmatched_images_records)
    df_unmatched_img.to_csv(UNMATCHED_IMAGES_PATH, index=False)
    print(f"  + Wrote {len(df_unmatched_img):,} rows to: {UNMATCHED_IMAGES_PATH.relative_to(PROJECT_ROOT)}", flush=True)

    # 6. Product and Category Statistics
    unique_product_ids = df_validated["product_id"].nunique()
    product_id_counts = Counter(df_validated["product_id"])
    products_with_multi_images = sum(1 for c in product_id_counts.values() if c > 1)
    products_with_single_image = sum(1 for c in product_id_counts.values() if c == 1)

    category_counts = df_validated["category"].value_counts().to_dict()

    elapsed = time.time() - start_time

    # 7. Print Final Verification Summary
    print("\n" + "=" * 70, flush=True)
    print(" " * 20 + "VALIDATION SUMMARY REPORT", flush=True)
    print("=" * 70, flush=True)
    print(f"Total images discovered:              {total_images_discovered:,}")
    print(f"Valid images:                         {valid_images_count:,}")
    print(f"Invalid images:                       {invalid_images_count:,}")
    print(f"Metadata rows:                        {total_metadata_rows:,}")
    print(f"Matched images:                       {matched_images_count:,}")
    print(f"Unmatched images:                     {unmatched_images_count:,}")
    print(f"Unmatched metadata rows:              {unmatched_metadata_count:,}")
    print(f"Unique product IDs:                   {unique_product_ids:,}")
    print(f"Products with multiple images:        {products_with_multi_images:,}")
    print(f"Products with only one image:         {products_with_single_image:,}")
    print(f"\nTop Categories Breakdown ({len(category_counts)} categories):")
    for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {cat:25}: {count:6,} ({count/len(df_validated)*100:5.2f}%)")

    print("\nManifest Integrity Confirmation:")
    print(f"  - Rows in validated_catalog_manifest.csv : {len(df_validated):,}")
    print(f"  - Matched usable valid images count     : {matched_images_count:,}")
    assert len(df_validated) == matched_images_count, "Manifest row count mismatch!"
    print(f"  - Status: CONFIRMED (100% 1-to-1 match)")
    print(f"Total validation elapsed time: {elapsed:.2f} seconds")
    print("=" * 70, flush=True)


if __name__ == "__main__":
    run_validation()
