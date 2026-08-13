"""Script to prepare evaluation dataset: query images and ground_truth.csv."""

import csv
from pathlib import Path
import shutil
import sys

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_all_products

EVALUATION_DIR = PROJECT_ROOT / "data" / "evaluation"
QUERIES_DIR = EVALUATION_DIR / "queries"
GROUND_TRUTH_FILE = EVALUATION_DIR / "ground_truth.csv"


def main() -> None:
    print("Preparing evaluation dataset...")
    QUERIES_DIR.mkdir(parents=True, exist_ok=True)

    products = fetch_all_products()
    if not products:
        print("Error: No products found in SQLite database.", file=sys.stderr)
        sys.exit(1)

    # Select up to 20 query items for evaluation dataset
    query_products = products[:20]
    rows = []

    print(f"Copying {len(query_products)} query images to: {QUERIES_DIR}")

    for idx, prod in enumerate(query_products, start=1):
        src_path = Path(prod["image_path"])
        query_filename = f"query_{idx:02d}_{prod['filename']}"
        dst_path = QUERIES_DIR / query_filename

        if src_path.exists():
            shutil.copy2(src_path, dst_path)
            rows.append(
                {
                    "query_filename": query_filename,
                    "ground_truth_product_id": prod["id"],
                    "ground_truth_external_id": prod["external_id"],
                    "category": prod["category"],
                }
            )
        else:
            print(f"Warning: Source image '{src_path}' not found.", file=sys.stderr)

    # Write ground_truth.csv
    fieldnames = ["query_filename", "ground_truth_product_id", "ground_truth_external_id", "category"]
    with open(GROUND_TRUTH_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Created ground truth CSV ({len(rows)} records) at: {GROUND_TRUTH_FILE}")
    print("Evaluation dataset prepared successfully.")


if __name__ == "__main__":
    main()
