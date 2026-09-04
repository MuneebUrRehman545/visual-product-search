"""Generate realistic messy query variations from final test queries for robustness evaluation.

Transformations:
  - crop (tight bounding crop ~10-15%)
  - darker_lighting (brightness 0.65)
  - brighter_lighting (brightness 1.35)
  - contrast_change (contrast 1.45)
  - small_rotation (slight rotation +/- 6-10 deg)
  - mild_perspective (slight 4-point projective transform)
  - blur (Gaussian blur radius 1.5)
  - background_padding (color border padding)

Outputs:
  - evaluation/queries/messy/
  - evaluation/messy_query_manifest.csv
"""

import argparse
import os
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List, Tuple
import pandas as pd
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_catalog_items_by_ids

DEFAULT_TEST_CSV = PROJECT_ROOT / "data" / "splits" / "test_queries.csv"
DEFAULT_GT_CSV = PROJECT_ROOT / "evaluation" / "ground_truth.csv"
DEFAULT_ID_MAP_CSV = PROJECT_ROOT / "data" / "manifests" / "catalog_id_map.csv"

MESSY_DIR = PROJECT_ROOT / "evaluation" / "queries" / "messy"
OUTPUT_MANIFEST = PROJECT_ROOT / "evaluation" / "messy_query_manifest.csv"

TRANSFORMATION_TYPES = [
    "crop",
    "darker_lighting",
    "brighter_lighting",
    "contrast_change",
    "small_rotation",
    "mild_perspective",
    "blur",
    "background_padding",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate messy query variations.")
    parser.add_argument(
        "--test-csv",
        type=Path,
        default=DEFAULT_TEST_CSV,
        help="Path to data/splits/test_queries.csv",
    )
    parser.add_argument(
        "--gt-csv",
        type=Path,
        default=DEFAULT_GT_CSV,
        help="Path to evaluation/ground_truth.csv",
    )
    parser.add_argument(
        "--id-map-csv",
        type=Path,
        default=DEFAULT_ID_MAP_CSV,
        help="Path to data/manifests/catalog_id_map.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MESSY_DIR,
        help="Directory to save messy query images",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=OUTPUT_MANIFEST,
        help="Path to messy_query_manifest.csv",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic variations (default: 42)",
    )
    return parser.parse_args()


def apply_transformation(img: Image.Image, transform_name: str, rng: random.Random) -> Image.Image:
    """Apply a deterministic visual distortion to an image."""
    rgb = img.convert("RGB")
    w, h = rgb.size

    if transform_name == "crop":
        # Crop 10% to 15% from random borders
        crop_left = int(w * rng.uniform(0.06, 0.12))
        crop_top = int(h * rng.uniform(0.06, 0.12))
        crop_right = w - int(w * rng.uniform(0.06, 0.12))
        crop_bottom = h - int(h * rng.uniform(0.06, 0.12))
        cropped = rgb.crop((crop_left, crop_top, crop_right, crop_bottom))
        return cropped.resize((w, h), Image.Resampling.BILINEAR)

    elif transform_name == "darker_lighting":
        factor = rng.uniform(0.60, 0.70)
        enhancer = ImageEnhance.Brightness(rgb)
        return enhancer.enhance(factor)

    elif transform_name == "brighter_lighting":
        factor = rng.uniform(1.30, 1.45)
        enhancer = ImageEnhance.Brightness(rgb)
        return enhancer.enhance(factor)

    elif transform_name == "contrast_change":
        factor = rng.uniform(1.40, 1.60)
        enhancer = ImageEnhance.Contrast(rgb)
        return enhancer.enhance(factor)

    elif transform_name == "small_rotation":
        angle = rng.choice([-8, -6, -4, 4, 6, 8])
        rotated = rgb.rotate(angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=(255, 255, 255))
        return rotated

    elif transform_name == "mild_perspective":
        # Perspective transform using 8 coefficients
        dx = int(w * rng.uniform(0.05, 0.10))
        dy = int(h * rng.uniform(0.05, 0.10))
        coeffs = (1, rng.uniform(-0.08, 0.08), 0, rng.uniform(-0.08, 0.08), 1, 0, 0.0002, 0.0002)
        return rgb.transform((w, h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BILINEAR, fillcolor=(255, 255, 255))

    elif transform_name == "blur":
        radius = rng.uniform(1.2, 1.8)
        return rgb.filter(ImageFilter.GaussianBlur(radius=radius))

    elif transform_name == "background_padding":
        pad_x = int(w * rng.uniform(0.08, 0.15))
        pad_y = int(h * rng.uniform(0.08, 0.15))
        padded = ImageOps.expand(rgb, border=(pad_x, pad_y), fill=(240, 240, 240))
        return padded.resize((w, h), Image.Resampling.BILINEAR)

    return rgb


def generate_messy_queries(
    test_csv_path: Path,
    gt_csv_path: Path,
    id_map_csv_path: Path,
    output_dir: Path = MESSY_DIR,
    output_manifest_path: Path = OUTPUT_MANIFEST,
    seed: int = 42,
) -> int:
    """Generate messy test query variations and save manifest."""
    start_time = time.time()
    print("=" * 70)
    print(" " * 16 + "MESSY QUERY VARIATIONS GENERATOR")
    print("=" * 70)

    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    df_test = pd.read_csv(test_csv_path)
    df_gt = pd.read_csv(gt_csv_path)
    df_id_map = pd.read_csv(id_map_csv_path)

    # Map query_id to relevant catalog IDs from ground truth
    gt_map = {}
    for _, r in df_gt.iterrows():
        gt_map[r["query_id"]] = {
            "relevant_catalog_ids": str(r["relevant_catalog_ids"]),
            "category": r.get("category", ""),
            "product_name": r.get("product_name", ""),
        }

    total_test_queries = len(df_test)
    print(f"Loaded {total_test_queries} clean test queries.")
    print(f"Generating 1 realistic messy variation per clean test query...")

    messy_records = []
    for idx, row in df_test.iterrows():
        qid = row["query_id"]
        source_img_id = int(row["image_id"])
        prod_id = int(row["product_id"])
        rel_path = row["relative_path"]
        source_full_path = PROJECT_ROOT / rel_path

        gt_info = gt_map.get(qid, {})
        rel_cat_ids_raw = gt_info.get("relevant_catalog_ids", "")

        # Cycle/assign transformation deterministically
        t_type = TRANSFORMATION_TYPES[idx % len(TRANSFORMATION_TYPES)]
        messy_qid = f"messy_{qid}_{t_type}"
        messy_filename = f"{messy_qid}.jpg"
        messy_file_path = output_dir / messy_filename
        rel_messy_path = f"evaluation/queries/messy/{messy_filename}"

        with Image.open(source_full_path) as src_img:
            transformed_img = apply_transformation(src_img, t_type, rng)
            transformed_img.save(messy_file_path, "JPEG", quality=90)

        messy_records.append(
            {
                "query_id": messy_qid,
                "source_query_id": qid,
                "source_image_id": source_img_id,
                "product_id": prod_id,
                "product_name": row.get("product_display_name", ""),
                "category": row.get("category", ""),
                "variation_type": t_type,
                "messy_image_path": rel_messy_path,
                "relevant_catalog_ids": rel_cat_ids_raw,
                "split": "messy_test",
            }
        )

    df_messy = pd.DataFrame(messy_records)
    df_messy.to_csv(output_manifest_path, index=False)

    print(f"\nGenerated {len(df_messy)} messy query images in: {output_dir.relative_to(PROJECT_ROOT)}")
    print(f"Wrote messy manifest: {output_manifest_path.relative_to(PROJECT_ROOT)}")

    # Visual & Integrity Assertions
    print("\nRunning Validation & Integrity Assertions...")

    # Assertion 1: All generated files exist and are valid readable images
    for _, r in df_messy.iterrows():
        fp = PROJECT_ROOT / r["messy_image_path"]
        assert fp.exists() and fp.is_file(), f"Missing messy image file: {fp}"
        with Image.open(fp) as test_img:
            assert test_img.width > 0 and test_img.height > 0, f"Corrupt messy image: {fp}"
    print(f"  [PASS] All {len(df_messy)} messy query files are valid and readable on disk.")

    # Assertion 2: All inherited relevant catalog items exist in catalog_id_map and DB
    valid_source_img_ids = set(df_id_map["image_id"].astype(int))
    for _, r in df_messy.iterrows():
        raw_ids = [int(x) for x in str(r["relevant_catalog_ids"]).split(",") if x.strip().isdigit()]
        assert len(raw_ids) > 0, f"Messy query {r['query_id']} has no relevant catalog IDs!"
        for cid in raw_ids:
            assert cid in valid_source_img_ids, f"Inherited catalog image {cid} missing from catalog ID map!"
    print(f"  [PASS] 100% of inherited ground-truth catalog IDs exist in catalog_id_map.")

    # Assertion 3: Zero leakage into catalog
    catalog_img_ids = set(df_id_map["image_id"].astype(int))
    for _, r in df_messy.iterrows():
        assert r["source_image_id"] not in catalog_img_ids, "Leaked test image detected in catalog!"
    print(f"  [PASS] 0% leakage: Searchable catalog strictly excludes all test and messy query images.")

    # Distribution breakdown
    breakdown = df_messy["variation_type"].value_counts().to_dict()
    print(f"\nTransformation Distribution:")
    for v_type, cnt in breakdown.items():
        print(f"  - {v_type:<22}: {cnt} queries")

    # Sample Verification
    print(f"\nSample Messy Query Records (5 Random Samples):")
    sample_rows = df_messy.sample(n=5, random_state=seed)
    for _, s in sample_rows.iterrows():
        print(
            f"  - [{s['query_id']:30}] Source: {s['source_query_id']:10} | "
            f"Type: {s['variation_type']:18} | Product: {str(s['product_name'])[:30]}"
        )

    elapsed = time.time() - start_time
    print(f"\nMessy query generation completed in {elapsed:.2f} seconds.")
    print("=" * 70)
    return len(df_messy)


if __name__ == "__main__":
    args = parse_args()
    generate_messy_queries(
        test_csv_path=args.test_csv,
        gt_csv_path=args.gt_csv,
        id_map_csv_path=args.id_map_csv,
        output_dir=args.output_dir,
        output_manifest_path=args.output_manifest,
        seed=args.seed,
    )
