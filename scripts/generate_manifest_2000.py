"""Script to generate data/catalog/manifest_2000.csv manifest."""

import csv
import os
from pathlib import Path
import sys
import pandas as pd
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STYLES_CSV = (
    Path(os.getenv("STYLES_CSV")).resolve()
    if os.getenv("STYLES_CSV")
    else PROJECT_ROOT / "data" / "styles.csv"
)
RAW_IMAGES_DIR = (
    Path(os.getenv("RAW_IMAGES_DIR")).resolve()
    if os.getenv("RAW_IMAGES_DIR")
    else PROJECT_ROOT / "data" / "images"
)
OUTPUT_MANIFEST = PROJECT_ROOT / "data" / "catalog" / "manifest_2000.csv"


def main() -> None:
    print(f"Loading metadata from {STYLES_CSV}...")
    if not STYLES_CSV.exists():
        print(f"Error: Metadata file '{STYLES_CSV}' not found.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(STYLES_CSV, on_bad_lines="skip")
    df.columns = [str(col).strip() for col in df.columns]

    print(f"Total metadata rows: {len(df)}")

    valid_rows = []
    seen_ids = set()

    # Sort deterministically by id
    df["id_numeric"] = pd.to_numeric(df["id"], errors="coerce")
    df = df.dropna(subset=["id_numeric"]).sort_values(by="id_numeric").reset_index(drop=True)

    for _, row in df.iterrows():
        prod_id = str(int(row["id_numeric"]))

        if prod_id in seen_ids:
            continue

        img_name = f"{prod_id}.jpg"
        img_path = RAW_IMAGES_DIR / img_name

        if not img_path.exists() or img_path.stat().st_size == 0:
            continue

        try:
            with Image.open(img_path) as img:
                img.verify()
        except Exception:
            continue

        category = str(row.get("articleType", row.get("masterCategory", "general"))).strip()
        if not category or category == "nan":
            category = "general"

        rel_image_path = f"images/{img_name}"

        valid_rows.append({
            "product_id": prod_id,
            "image_path": rel_image_path,
            "filename": img_name,
            "category": category,
        })

        seen_ids.add(prod_id)

        if len(valid_rows) == 2000:
            break

    print(f"Collected {len(valid_rows)} valid product entries.")

    if len(valid_rows) < 2000:
        print(f"Error: Could only collect {len(valid_rows)} valid images (2000 required).", file=sys.stderr)
        sys.exit(1)

    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["product_id", "image_path", "filename", "category"]

    with open(OUTPUT_MANIFEST, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(valid_rows)

    print(f"Successfully generated manifest ({len(valid_rows)} rows) at: {OUTPUT_MANIFEST}")


if __name__ == "__main__":
    main()
