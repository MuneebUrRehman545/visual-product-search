"""Create leakage-free catalog, validation query, and final test splits for Week 3.

Processes validated_catalog_manifest.csv to extract:
1. data/splits/catalog.csv: Searchable catalog images.
2. data/splits/validation_queries.csv: 100 validation queries for parameter tuning.
3. data/splits/test_queries.csv: 200 final test queries for benchmark reporting.
4. data/splits/split_summary.json: Metadata summary of the split.
5. evaluation/ground_truth_candidates.csv: Ground truth relevance mappings.

Ensures zero leakage: No query image appears in catalog.csv, while alternate images
of the same product remain in catalog.csv to serve as ground-truth retrieval targets.
"""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random
import sys
from typing import Any, Dict, List, Set, Tuple
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "manifests" / "validated_catalog_manifest.csv"
DEFAULT_SPLITS_DIR = PROJECT_ROOT / "data" / "splits"
DEFAULT_GROUND_TRUTH = PROJECT_ROOT / "evaluation" / "ground_truth_candidates.csv"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Create leakage-free dataset splits.")
    parser.add_argument(
        "--input-manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to validated_catalog_manifest.csv",
    )
    parser.add_argument(
        "--splits-dir",
        type=Path,
        default=DEFAULT_SPLITS_DIR,
        help="Output directory for split CSVs",
    )
    parser.add_argument(
        "--ground-truth-path",
        type=Path,
        default=DEFAULT_GROUND_TRUTH,
        help="Output path for ground truth candidates CSV",
    )
    parser.add_argument(
        "--val-count",
        type=int,
        default=100,
        help="Number of validation queries (default: 100)",
    )
    parser.add_argument(
        "--test-count",
        type=int,
        default=200,
        help="Number of final test queries (default: 200)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    return parser.parse_args()


def build_product_key(row: pd.Series) -> str:
    """Construct a clean, robust product grouping identifier."""
    name = str(row.get("product_display_name", "")).strip().lower()
    art = str(row.get("article_type", "")).strip().lower()
    gender = str(row.get("gender", "")).strip().lower()
    colour = str(row.get("base_colour", "")).strip().lower()

    if name and name != "unknown" and name != "nan":
        return f"{name}|{art}|{gender}|{colour}"
    return f"id_{row['image_id']}"


def create_splits(
    input_manifest_path: Path,
    splits_dir: Path,
    ground_truth_path: Path,
    val_count: int = 100,
    test_count: int = 200,
    seed: int = 42,
) -> Dict[str, Any]:
    """Execute stratified splitting and enforce leakage-free assertions."""
    print("=" * 70)
    print(" " * 18 + "DATASET SPLIT & GROUND TRUTH GENERATOR")
    print("=" * 70)
    print(f"Fixed Random Seed:        {seed}")
    print(f"Input Manifest:           {input_manifest_path.relative_to(PROJECT_ROOT)}")
    print(f"Target Validation Count:  {val_count}")
    print(f"Target Final Test Count:  {test_count}")
    print(f"Target Total Queries:     {val_count + test_count}")

    random.seed(seed)

    if not input_manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {input_manifest_path}")

    df = pd.read_csv(input_manifest_path)
    total_manifest_rows = len(df)
    print(f"\nLoaded {total_manifest_rows:,} validated items from manifest.")

    # 1. Group by Product Key
    df["product_key"] = df.apply(build_product_key, axis=1)

    # Group records by product_key
    products_map: Dict[str, List[Dict[str, Any]]] = {}
    for record in df.to_dict(orient="records"):
        key = record["product_key"]
        products_map.setdefault(key, []).append(record)

    # Separate eligible multi-image products (>= 2 images) from single-image products
    eligible_multi_products: Dict[str, List[Dict[str, Any]]] = {
        k: items for k, items in products_map.items() if len(items) >= 2
    }
    single_image_products: Dict[str, List[Dict[str, Any]]] = {
        k: items for k, items in products_map.items() if len(items) == 1
    }

    print(f"Total Unique Product Groups:         {len(products_map):,}")
    print(f"Multi-Image Eligible Products (>=2): {len(eligible_multi_products):,}")
    print(f"Single-Image Products (=1):          {len(single_image_products):,}")

    total_target_queries = val_count + test_count
    if len(eligible_multi_products) < total_target_queries:
        raise ValueError(
            f"Insufficient multi-image products ({len(eligible_multi_products)}) for requested query count ({total_target_queries})."
        )

    # 2. Stratified Sampling across Categories
    # Group eligible products by category
    category_to_keys: Dict[str, List[str]] = {}
    for key, items in eligible_multi_products.items():
        cat = items[0].get("category", "Unknown")
        category_to_keys.setdefault(cat, []).append(key)

    # Sort keys within each category deterministically before shuffling
    for cat in category_to_keys:
        category_to_keys[cat].sort()
        random.Random(seed).shuffle(category_to_keys[cat])

    selected_query_keys: List[str] = []
    # Proportional category allocation
    total_multi = len(eligible_multi_products)
    allocation: Dict[str, int] = {}
    allocated_sum = 0
    for cat, keys in sorted(category_to_keys.items()):
        count = int(round((len(keys) / total_multi) * total_target_queries))
        allocation[cat] = min(count, len(keys))
        allocated_sum += allocation[cat]

    # Adjust rounding if needed
    diff = total_target_queries - allocated_sum
    sorted_cats_by_pool = sorted(category_to_keys.keys(), key=lambda c: len(category_to_keys[c]), reverse=True)
    while diff != 0:
        for cat in sorted_cats_by_pool:
            if diff > 0 and allocation[cat] < len(category_to_keys[cat]):
                allocation[cat] += 1
                diff -= 1
                if diff == 0:
                    break
            elif diff < 0 and allocation[cat] > 0:
                allocation[cat] -= 1
                diff += 1
                if diff == 0:
                    break

    print(f"\nStratified Category Allocation for {total_target_queries} Queries:")
    for cat, count in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {cat:20}: {count:3} queries (from pool of {len(category_to_keys[cat]):,} multi-image products)")
        selected_query_keys.extend(category_to_keys[cat][:count])

    # Shuffle the selected keys deterministically
    random.Random(seed + 1).shuffle(selected_query_keys)

    # 3. Partition into Validation (val_count) and Test (test_count)
    val_keys = set(selected_query_keys[:val_count])
    test_keys = set(selected_query_keys[val_count : val_count + test_count])

    assert len(val_keys) == val_count, "Validation key count mismatch!"
    assert len(test_keys) == test_count, "Test key count mismatch!"
    assert val_keys.isdisjoint(test_keys), "Validation and Test product keys must be disjoint!"

    # 4. Construct Catalog, Validation Queries, Test Queries, and Ground Truth
    catalog_records: List[Dict[str, Any]] = []
    val_query_records: List[Dict[str, Any]] = []
    test_query_records: List[Dict[str, Any]] = []
    ground_truth_records: List[Dict[str, Any]] = []

    val_query_idx = 1
    test_query_idx = 1

    query_image_ids: Set[int] = set()
    query_image_paths: Set[str] = set()

    for product_key, items in products_map.items():
        if product_key in val_keys:
            # Sort items deterministically by image_id
            items_sorted = sorted(items, key=lambda x: x["image_id"])
            # Pick 1 image deterministically as validation query
            rng = random.Random(f"{seed}_val_{product_key}")
            query_item = rng.choice(items_sorted)
            remaining_catalog_items = [it for it in items_sorted if it["image_id"] != query_item["image_id"]]

            query_id = f"val_q{val_query_idx:03d}"
            val_query_idx += 1

            query_rec = dict(query_item)
            query_rec["query_id"] = query_id
            query_rec["split"] = "validation"
            val_query_records.append(query_rec)
            query_image_ids.add(query_item["image_id"])
            query_image_paths.add(query_item["relative_path"])

            # Remaining items go to catalog
            for cat_item in remaining_catalog_items:
                catalog_records.append(cat_item)

            # Record ground truth candidates
            relevant_catalog_ids = [str(it["image_id"]) for it in remaining_catalog_items]
            ground_truth_records.append(
                {
                    "query_id": query_id,
                    "query_image_id": query_item["image_id"],
                    "query_filename": query_item["filename"],
                    "query_path": query_item["relative_path"],
                    "product_id": query_item["product_id"],
                    "product_key": product_key,
                    "split": "validation",
                    "category": query_item.get("category", ""),
                    "article_type": query_item.get("article_type", ""),
                    "product_name": query_item.get("product_display_name", ""),
                    "relevant_catalog_item_ids": ",".join(relevant_catalog_ids),
                    "relevant_catalog_count": len(relevant_catalog_ids),
                }
            )

        elif product_key in test_keys:
            items_sorted = sorted(items, key=lambda x: x["image_id"])
            rng = random.Random(f"{seed}_test_{product_key}")
            query_item = rng.choice(items_sorted)
            remaining_catalog_items = [it for it in items_sorted if it["image_id"] != query_item["image_id"]]

            query_id = f"test_q{test_query_idx:03d}"
            test_query_idx += 1

            query_rec = dict(query_item)
            query_rec["query_id"] = query_id
            query_rec["split"] = "test"
            test_query_records.append(query_rec)
            query_image_ids.add(query_item["image_id"])
            query_image_paths.add(query_item["relative_path"])

            for cat_item in remaining_catalog_items:
                catalog_records.append(cat_item)

            relevant_catalog_ids = [str(it["image_id"]) for it in remaining_catalog_items]
            ground_truth_records.append(
                {
                    "query_id": query_id,
                    "query_image_id": query_item["image_id"],
                    "query_filename": query_item["filename"],
                    "query_path": query_item["relative_path"],
                    "product_id": query_item["product_id"],
                    "product_key": product_key,
                    "split": "test",
                    "category": query_item.get("category", ""),
                    "article_type": query_item.get("article_type", ""),
                    "product_name": query_item.get("product_display_name", ""),
                    "relevant_catalog_item_ids": ",".join(relevant_catalog_ids),
                    "relevant_catalog_count": len(relevant_catalog_ids),
                }
            )

        else:
            # Non-query products (all items stay in catalog)
            for item in items:
                catalog_records.append(item)

    # 5. Convert to DataFrames
    df_catalog = pd.DataFrame(catalog_records)
    df_val = pd.DataFrame(val_query_records)
    df_test = pd.DataFrame(test_query_records)
    df_gt = pd.DataFrame(ground_truth_records)

    # 6. HARD LEAKAGE & INTEGRITY ASSERTIONS
    print("\nExecuting Hard Leakage & Dataset Integrity Assertions...")

    # Assertion 1: No query image appears in catalog
    catalog_image_ids = set(df_catalog["image_id"])
    catalog_paths = set(df_catalog["relative_path"])
    leaked_ids = query_image_ids.intersection(catalog_image_ids)
    leaked_paths = query_image_paths.intersection(catalog_paths)

    if leaked_ids:
        raise AssertionError(f"FATAL: Query image IDs leaked into catalog: {leaked_ids}")
    if leaked_paths:
        raise AssertionError(f"FATAL: Query image paths leaked into catalog: {leaked_paths}")
    print("  [PASS] Zero query image leakage into catalog (0 leaked images).")

    # Assertion 2: No duplicate query IDs
    all_query_ids = list(df_val["query_id"]) + list(df_test["query_id"])
    assert len(all_query_ids) == len(set(all_query_ids)), "Duplicate query IDs detected!"
    print("  [PASS] Unique query IDs verified across validation and test.")

    # Assertion 3: No query path appears in both validation and test
    val_paths = set(df_val["relative_path"])
    test_paths = set(df_test["relative_path"])
    assert val_paths.isdisjoint(test_paths), "Query path shared between validation and test!"
    print("  [PASS] Disjoint query paths between validation and test.")

    # Assertion 4: Validation and test product IDs are disjoint
    val_pids = set(df_val["product_key"])
    test_pids = set(df_test["product_key"])
    assert val_pids.isdisjoint(test_pids), "Validation and test product keys are not disjoint!"
    print("  [PASS] Disjoint product keys between validation and test.")

    # Assertion 5: Every clean query has at least 1 valid catalog ground-truth match
    for _, gt_row in df_gt.iterrows():
        rel_ids = [int(x) for x in gt_row["relevant_catalog_item_ids"].split(",") if x]
        assert len(rel_ids) >= 1, f"Query {gt_row['query_id']} has no catalog ground truth matches!"
        for rid in rel_ids:
            assert rid in catalog_image_ids, f"Relevant ID {rid} for {gt_row['query_id']} is missing from catalog!"
    print("  [PASS] 100% of queries have at least 1 valid catalog ground-truth match.")

    # Assertion 6: Every catalog and query file physically exists on disk
    for rel_p in df_catalog["relative_path"]:
        full_p = PROJECT_ROOT / rel_p
        assert full_p.exists(), f"Catalog image file missing on disk: {full_p}"

    for rel_p in list(df_val["relative_path"]) + list(df_test["relative_path"]):
        full_p = PROJECT_ROOT / rel_p
        assert full_p.exists(), f"Query image file missing on disk: {full_p}"
    print("  [PASS] 100% physical existence verified for catalog and query image files.")

    # Assertion 7: Total item count conservation
    total_split_items = len(df_catalog) + len(df_val) + len(df_test)
    assert total_split_items == total_manifest_rows, (
        f"Item count mismatch: Catalog ({len(df_catalog)}) + Val ({len(df_val)}) + "
        f"Test ({len(df_test)}) = {total_split_items} != Total Manifest ({total_manifest_rows})"
    )
    print(f"  [PASS] Total item count conservation confirmed ({total_split_items:,} items).")

    # 7. Save Artifacts to Disk
    splits_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_path.parent.mkdir(parents=True, exist_ok=True)

    catalog_csv_path = splits_dir / "catalog.csv"
    val_csv_path = splits_dir / "validation_queries.csv"
    test_csv_path = splits_dir / "test_queries.csv"
    summary_json_path = splits_dir / "split_summary.json"

    df_catalog.to_csv(catalog_csv_path, index=False)
    df_val.to_csv(val_csv_path, index=False)
    df_test.to_csv(test_csv_path, index=False)
    df_gt.to_csv(ground_truth_path, index=False)

    print(f"\nSaved split files:")
    print(f"  + Catalog CSV:           {catalog_csv_path.relative_to(PROJECT_ROOT)} ({len(df_catalog):,} rows)")
    print(f"  + Validation Queries:    {val_csv_path.relative_to(PROJECT_ROOT)} ({len(df_val):,} rows)")
    print(f"  + Final Test Queries:    {test_csv_path.relative_to(PROJECT_ROOT)} ({len(df_test):,} rows)")
    print(f"  + Ground Truth Mappings: {ground_truth_path.relative_to(PROJECT_ROOT)} ({len(df_gt):,} rows)")

    # 8. Create Summary JSON
    summary_data = {
        "random_seed": seed,
        "total_manifest_records": total_manifest_rows,
        "searchable_catalog_size": len(df_catalog),
        "validation_queries_count": len(df_val),
        "final_test_queries_count": len(df_test),
        "total_queries_count": len(df_val) + len(df_test),
        "leakage_check": "PASSED (0 query images in catalog)",
        "ground_truth_stats": {
            "total_query_records": len(df_gt),
            "min_matches_per_query": int(df_gt["relevant_catalog_count"].min()),
            "max_matches_per_query": int(df_gt["relevant_catalog_count"].max()),
            "mean_matches_per_query": round(float(df_gt["relevant_catalog_count"].mean()), 2),
            "median_matches_per_query": round(float(df_gt["relevant_catalog_count"].median()), 2),
        },
        "category_distribution": {
            "catalog": df_catalog["category"].value_counts().to_dict(),
            "validation_queries": df_val["category"].value_counts().to_dict(),
            "test_queries": df_test["category"].value_counts().to_dict(),
        },
    }

    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f"  + Split Summary JSON:    {summary_json_path.relative_to(PROJECT_ROOT)}")

    # 9. Print Final Summary Report
    print("\n" + "=" * 70)
    print(" " * 20 + "SPLIT GENERATION REPORT")
    print("=" * 70)
    print(f"Random Seed:                          {seed}")
    print(f"Searchable Catalog Size:              {len(df_catalog):,} images")
    print(f"Validation Queries Count:             {len(df_val):,} queries")
    print(f"Final Test Queries Count:             {len(df_test):,} queries")
    print(f"Total Queries Generated:              {len(df_gt):,} queries")
    print(f"Categories Represented in Queries:    {df_gt['category'].nunique()} categories")
    print(f"Ground Truth Matches per Query (Mean): {summary_data['ground_truth_stats']['mean_matches_per_query']} matches (Min: {summary_data['ground_truth_stats']['min_matches_per_query']}, Max: {summary_data['ground_truth_stats']['max_matches_per_query']})")
    print(f"Leakage Check:                        PASSED (Zero Query Overlap)")
    print("=" * 70)

    return summary_data


if __name__ == "__main__":
    args = parse_args()
    create_splits(
        input_manifest_path=args.input_manifest,
        splits_dir=args.splits_dir,
        ground_truth_path=args.ground_truth_path,
        val_count=args.val_count,
        test_count=args.test_count,
        seed=args.seed,
    )
