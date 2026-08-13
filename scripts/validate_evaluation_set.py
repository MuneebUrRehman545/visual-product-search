"""Script to validate evaluation set schema, image files, and SQLite ground-truth IDs."""

import csv
from pathlib import Path
import sys
from typing import List, Set

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_all_products, get_connection

GROUND_TRUTH_CSV = PROJECT_ROOT / "evaluation" / "ground_truth.csv"

ALLOWED_VARIATIONS: Set[str] = {
    "clean",
    "different_crop",
    "changed_background",
    "cluttered_background",
    "different_lighting",
    "partial_object",
    "different_angle",
    "visually_similar",
    "phone_camera",
}


def load_valid_db_product_ids() -> Set[int]:
    """Retrieve set of all valid SQLite products.id values."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT id FROM products;")
        return {row["id"] for row in cursor.fetchall()}


def validate_evaluation_set() -> bool:
    print("=" * 80)
    print("VALIDATING EVALUATION SET INTEGRITY")
    print("=" * 80)
    print(f"Ground Truth CSV: {GROUND_TRUTH_CSV}\n")

    if not GROUND_TRUTH_CSV.exists():
        print(f"ERROR: Ground truth CSV file not found at '{GROUND_TRUTH_CSV}'", file=sys.stderr)
        return False

    db_ids = load_valid_db_product_ids()
    print(f"Loaded {len(db_ids)} valid product IDs from SQLite database.")

    query_ids_seen: Set[str] = set()
    raw_rows_seen: Set[str] = set()
    errors: List[str] = []
    warnings: List[str] = []
    total_rows = 0

    with open(GROUND_TRUTH_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate CSV Header
        expected_columns = ["query_id", "query_image", "relevant_product_ids", "variation_type", "notes"]
        if reader.fieldnames != expected_columns:
            errors.append(f"Header mismatch. Expected {expected_columns}, got {reader.fieldnames}")

        for line_num, row in enumerate(reader, start=2):
            total_rows += 1
            row_str = str(dict(row))

            # 1. Check duplicate rows
            if row_str in raw_rows_seen:
                errors.append(f"Line {line_num}: Duplicate row detected -> {row_str}")
            raw_rows_seen.add(row_str)

            query_id = row.get("query_id", "").strip()
            query_image = row.get("query_image", "").strip()
            rel_pids_str = row.get("relevant_product_ids", "").strip()
            variation_type = row.get("variation_type", "").strip()

            # 2. Empty required fields check
            if not query_id:
                errors.append(f"Line {line_num}: Empty 'query_id'")
            if not query_image:
                errors.append(f"Line {line_num}: Empty 'query_image'")
            if not rel_pids_str:
                errors.append(f"Line {line_num}: Empty 'relevant_product_ids'")
            if not variation_type:
                errors.append(f"Line {line_num}: Empty 'variation_type'")

            # 3. Unique query_id check
            if query_id:
                if query_id in query_ids_seen:
                    errors.append(f"Line {line_num}: Duplicate query_id '{query_id}'")
                query_ids_seen.add(query_id)

            # 4. Query image existence check
            if query_image:
                img_path = PROJECT_ROOT / query_image
                if not img_path.exists() or not img_path.is_file():
                    errors.append(f"Line {line_num}: Referenced query_image file '{query_image}' not found on disk")

            # 5. Product ID format and DB existence check
            if rel_pids_str:
                # Support comma or semicolon separation
                raw_pids = rel_pids_str.replace(";", ",").split(",")
                for raw_pid in raw_pids:
                    pid_str = raw_pid.strip()
                    if not pid_str:
                        continue
                    try:
                        pid = int(pid_str)
                        if pid not in db_ids:
                            errors.append(f"Line {line_num}: relevant_product_id '{pid}' does not exist in SQLite products table")
                    except ValueError:
                        errors.append(f"Line {line_num}: Malformed product ID '{pid_str}' (must be integer)")

            # 6. Variation type check
            if variation_type and variation_type not in ALLOWED_VARIATIONS:
                errors.append(f"Line {line_num}: Unknown variation_type '{variation_type}'. Allowed: {sorted(ALLOWED_VARIATIONS)}")

    print(f"\nProcessed {total_rows} evaluation query record(s).")

    if errors:
        print("\n" + "=" * 80)
        print(f"VALIDATION FAILED WITH {len(errors)} ERROR(S):")
        for err in errors:
            print(f"  - {err}")
        print("=" * 80)
        return False
    else:
        print("\n" + "=" * 80)
        print("VALIDATION PASSED: All query IDs, image paths, product IDs, and variation types are valid.")
        print("=" * 80)
        return True


if __name__ == "__main__":
    success = validate_evaluation_set()
    sys.exit(0 if success else 1)
