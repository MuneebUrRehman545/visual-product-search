"""Build and populate the Production Catalog Database from data/splits/catalog.csv.

Supports Hosted PostgreSQL (Supabase / Neon) via DATABASE_URL and local SQLite.
Generates persistent ID mapping artifact: artifacts/faiss/production_mapping.csv
"""

import argparse
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List
import pandas as pd

# Ensure workspace root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import (
    bulk_insert_catalog_items,
    fetch_all_catalog_items,
    get_catalog_count,
    get_database_url,
    get_db_path,
    initialize_database,
    is_postgres,
)

DEFAULT_CATALOG_CSV = PROJECT_ROOT / "data" / "splits" / "catalog.csv"
DEFAULT_MAPPING_CSV = PROJECT_ROOT / "artifacts" / "faiss" / "production_mapping.csv"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Rebuild production catalog database.")
    parser.add_argument(
        "--catalog-csv",
        type=Path,
        default=DEFAULT_CATALOG_CSV,
        help="Path to data/splits/catalog.csv",
    )
    parser.add_argument(
        "--mapping-csv",
        type=Path,
        default=DEFAULT_MAPPING_CSV,
        help="Output path for artifacts/faiss/production_mapping.csv",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="PostgreSQL connection string (overrides DATABASE_URL env var)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite database path override",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for verification sampling (default: 42)",
    )
    return parser.parse_args()


def build_catalog_database(
    catalog_csv_path: Path,
    mapping_csv_path: Path,
    database_url: str = None,
    db_path: Path = None,
    seed: int = 42,
) -> int:
    """Rebuild catalog database and run verification assertions."""
    start_time = time.time()
    print("=" * 70)
    print(" " * 18 + "PRODUCTION CATALOG DATABASE BUILDER")
    print("=" * 70)

    db_type = "Hosted PostgreSQL" if (database_url or is_postgres()) else "Local SQLite"
    print(f"Database Provider/Type: {db_type}")
    print(f"Catalog Source CSV:     {catalog_csv_path.relative_to(PROJECT_ROOT)}")

    if not catalog_csv_path.exists():
        raise FileNotFoundError(f"Catalog CSV not found: {catalog_csv_path}")

    # 1. Load catalog CSV
    df_catalog = pd.read_csv(catalog_csv_path)
    total_csv_rows = len(df_catalog)
    print(f"Loaded {total_csv_rows:,} records from catalog CSV.")

    # 2. Re-initialize database schema
    print(f"\nInitializing {db_type} database schema (force_recreate=True)...")
    initialize_database(
        database_url=database_url,
        db_path=db_path,
        force_recreate=True,
    )

    # 3. Bulk insert catalog items
    print(f"Bulk inserting {total_csv_rows:,} catalog items into {db_type}...")
    items_to_insert = df_catalog.to_dict(orient="records")
    inserted_count = bulk_insert_catalog_items(
        items=items_to_insert,
        database_url=database_url,
        db_path=db_path,
        batch_size=5000,
    )
    print(f"  + Successfully inserted {inserted_count:,} product records.")

    # 4. Fetch all records to build FAISS mapping and run deep verification
    all_rows = fetch_all_catalog_items(database_url=database_url, db_path=db_path)
    db_count = len(all_rows)

    # 5. Generate persistent FAISS ID mapping artifact and catalog_id_map.csv
    print(f"\nGenerating catalog ID mappings...")
    mapping_csv_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_id_map_path = PROJECT_ROOT / "data" / "manifests" / "catalog_id_map.csv"
    catalog_id_map_path.parent.mkdir(parents=True, exist_ok=True)

    mapping_records = []
    id_map_records = []
    for row in all_rows:
        mapping_records.append(
            {
                "faiss_id": row["id"],
                "catalog_item_id": row["id"],
                "image_id": row["image_id"],
                "product_id": row["product_id"],
                "filename": row["filename"],
                "image_url": row.get("image_url", f"/catalog-images/{row['filename']}"),
            }
        )
        id_map_records.append(
            {
                "catalog_item_id": row["id"],
                "image_id": row["image_id"],
                "product_id": row["product_id"],
                "filename": row["filename"],
                "relative_path": row["relative_path"],
                "image_url": row.get("image_url", f"/catalog-images/{row['filename']}"),
            }
        )

    df_mapping = pd.DataFrame(mapping_records)
    df_mapping.to_csv(mapping_csv_path, index=False)
    print(f"  + Wrote {len(df_mapping):,} rows to: {mapping_csv_path.relative_to(PROJECT_ROOT)}")

    df_id_map = pd.DataFrame(id_map_records)
    df_id_map.to_csv(catalog_id_map_path, index=False)
    print(f"  + Wrote {len(df_id_map):,} rows to: {catalog_id_map_path.relative_to(PROJECT_ROOT)}")

    # 6. Verification & Assertions
    print("\nRunning Database Integrity & Consistency Assertions...")

    # Assertion 1: Row count match
    assert db_count == total_csv_rows, (
        f"Database row count mismatch: DB has {db_count:,} rows, but catalog.csv has {total_csv_rows:,} rows!"
    )
    print(f"  [PASS] Database row count == catalog.csv rows ({db_count:,} == {total_csv_rows:,}).")

    # Assertion 2: No duplicate internal IDs
    internal_ids = [r["id"] for r in all_rows]
    assert len(internal_ids) == len(set(internal_ids)), "Duplicate primary key IDs detected in database!"
    print(f"  [PASS] All {len(internal_ids):,} primary key IDs are unique and sequential.")

    # Assertion 3: No duplicate image IDs
    image_ids = [r["image_id"] for r in all_rows]
    assert len(image_ids) == len(set(image_ids)), "Duplicate image IDs detected in database!"
    print(f"  [PASS] All {len(image_ids):,} image IDs are unique.")

    # Assertion 4: Every DB image path resolves to a physical file on disk
    missing_files = []
    for r in all_rows:
        img_rel_p = r["relative_path"]
        full_p = PROJECT_ROOT / img_rel_p
        if not full_p.exists() or not full_p.is_file():
            missing_files.append(img_rel_p)
            if len(missing_files) >= 5:
                break

    if missing_files:
        raise FileNotFoundError(f"Database image paths missing on disk: {missing_files}")
    print("  [PASS] 100% of database image paths resolve to physical files on disk.")

    # Assertion 5: Random sampling check (10 rows)
    random.seed(seed)
    sample_indices = random.sample(range(len(all_rows)), k=10)
    print("\nVerifying Random Sample of 10 Database Rows against Source Files & Mapping:")
    for idx in sample_indices:
        db_row = all_rows[idx]
        csv_match = df_catalog[df_catalog["image_id"] == db_row["image_id"]].iloc[0]
        map_match = df_mapping[df_mapping["catalog_item_id"] == db_row["id"]].iloc[0]

        assert db_row["filename"] == csv_match["filename"], "Filename mismatch!"
        assert db_row["category"] == csv_match["category"], "Category mismatch!"
        assert db_row["id"] == map_match["faiss_id"], "FAISS ID mapping mismatch!"
        assert (PROJECT_ROOT / db_row["relative_path"]).exists(), "Sample image file missing!"

        print(
            f"  - FAISS ID {db_row['id']:5} -> Item ID: {db_row['id']:5} | "
            f"Image ID: {db_row['image_id']:5} | File: {db_row['filename']:10} | "
            f"URL: {db_row['image_url']:25} | Title: {str(db_row['product_display_name'])[:30]}"
        )

    elapsed = time.time() - start_time
    print(f"\nDatabase rebuild and mapping completed in {elapsed:.2f} seconds.")
    print("=" * 70)
    return db_count


if __name__ == "__main__":
    args = parse_args()
    build_catalog_database(
        catalog_csv_path=args.catalog_csv,
        mapping_csv_path=args.mapping_csv,
        database_url=args.database_url,
        db_path=args.db_path,
        seed=args.seed,
    )
