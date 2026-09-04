"""Dataset inspection and audit script for Visual Product Search (Week 3).

Discovers metadata files, counts image files, scans extensions, measures disk
footprint, profiles columns, and identifies ID/filename candidate mappings
without modifying any files or dataset assets.
"""

from collections import Counter
import os
from pathlib import Path
import sys
from typing import Dict, List, Optional, Set, Tuple
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def format_bytes(size_bytes: int) -> str:
    """Format bytes into a human-readable string (B, KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes / (1024**2):.2f} MB ({size_bytes:,} bytes)"
    else:
        return f"{size_bytes / (1024**3):.2f} GB ({size_bytes / (1024**2):.2f} MB / {size_bytes:,} bytes)"


def discover_metadata_file(data_path: Path) -> Optional[Path]:
    """Find Excel or CSV metadata files in the data directory."""
    if not data_path.exists():
        return None

    # Priority 1: Excel files (.xlsx, .xls)
    excel_files = list(data_path.glob("*.xlsx")) + list(data_path.glob("*.xls"))
    if excel_files:
        return excel_files[0]

    # Priority 2: CSV files (.csv)
    csv_files = [f for f in data_path.glob("*.csv") if f.is_file()]
    if csv_files:
        # Prefer styles.csv if present
        for f in csv_files:
            if f.name.lower() == "styles.csv":
                return f
        return csv_files[0]

    return None


def read_metadata(file_path: Path) -> Tuple[pd.DataFrame, List[str], str]:
    """Read metadata from Excel or CSV file and return dataframe, sheets, and format."""
    ext = file_path.suffix.lower()
    if ext in [".xlsx", ".xls"]:
        excel_obj = pd.ExcelFile(file_path)
        sheets = excel_obj.sheet_names
        df = pd.read_excel(file_path, sheet_name=sheets[0])
        return df, sheets, "Excel"
    else:
        df = pd.read_csv(file_path, on_bad_lines="skip")
        sheets = ["Default (CSV Table)"]
        return df, sheets, "CSV"


def audit_images(data_path: Path) -> Tuple[int, Set[str], int, Path, Dict[str, int]]:
    """Scan and count image files, extensions, and directory size."""
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
    image_counts_by_ext: Counter = Counter()
    total_images = 0
    total_image_bytes = 0
    images_dir = data_path / "images"

    scan_dir = images_dir if images_dir.exists() and images_dir.is_dir() else data_path

    for entry in os.scandir(scan_dir):
        if entry.is_file():
            ext = Path(entry.name).suffix.lower()
            if ext in image_extensions:
                total_images += 1
                image_counts_by_ext[ext] += 1
                total_image_bytes += entry.stat().st_size

    return total_images, set(image_counts_by_ext.keys()), total_image_bytes, scan_dir, dict(image_counts_by_ext)


def calculate_total_dataset_size(data_path: Path) -> int:
    """Calculate the total size of all files in the data directory in bytes."""
    total_bytes = 0
    for root, _, files in os.walk(data_path):
        for f in files:
            fp = Path(root) / f
            try:
                total_bytes += fp.stat().st_size
            except OSError:
                pass
    return total_bytes


def main() -> None:
    """Run comprehensive dataset discovery and print report."""
    print("=" * 70)
    print(" " * 20 + "DATASET INSPECTION REPORT")
    print("=" * 70)

    dataset_root = DATA_DIR.resolve()
    print(f"Dataset root: {dataset_root}")

    if not dataset_root.exists():
        print(f"[ERROR] Data directory does not exist at: {dataset_root}", file=sys.stderr)
        sys.exit(1)

    # 1. Discover metadata file
    meta_file = discover_metadata_file(dataset_root)
    if meta_file is None:
        print("[ERROR] No Excel or CSV metadata file found in data/ directory.", file=sys.stderr)
        sys.exit(1)

    rel_meta_path = meta_file.relative_to(PROJECT_ROOT)
    print(f"Excel file: {rel_meta_path} (Format: {meta_file.suffix})")

    # 2. Read metadata
    df, sheet_names, file_format = read_metadata(meta_file)
    print(f"Excel sheets: {', '.join(sheet_names)}")
    print(f"Metadata rows: {len(df):,}")
    print(f"Metadata columns count: {len(df.columns)}")

    # 3. Audit image files
    total_imgs, img_exts, img_bytes, img_location, ext_breakdown = audit_images(dataset_root)
    rel_img_location = img_location.relative_to(PROJECT_ROOT)
    print(f"Image location: {rel_img_location} (nested: {img_location != dataset_root})")
    print(f"Image files found: {total_imgs:,}")
    print(f"Image extensions: {', '.join(sorted(list(img_exts)))} {dict(ext_breakdown)}")

    # 4. Dataset size
    total_size = calculate_total_dataset_size(dataset_root)
    print(f"Dataset size: {format_bytes(total_size)}")
    print(f"Images size: {format_bytes(img_bytes)}")
    print(f"Metadata file size: {format_bytes(meta_file.stat().st_size)}")

    # 5. Column listing and candidate analysis
    print("\nExcel columns:")
    candidate_id_cols = []
    candidate_category_cols = []
    candidate_text_cols = []

    for col in df.columns:
        dtype = str(df[col].dtype)
        non_null = int(df[col].notnull().sum())
        null_count = int(df[col].isnull().sum())
        samples = [str(x) for x in df[col].dropna().unique()[:3]]
        sample_str = ", ".join(repr(s) for s in samples)
        print(f"  - {col:20} [dtype: {dtype:7} | non-null: {non_null:6,}/{len(df):,} | null: {null_count:5,}] -> Sample: [{sample_str}]")

        col_lower = col.lower()
        if "id" in col_lower or col_lower in ["code", "sku", "item"]:
            candidate_id_cols.append(col)
        if any(term in col_lower for term in ["category", "type", "article", "gender", "usage"]):
            candidate_category_cols.append(col)
        if any(term in col_lower for term in ["name", "title", "desc", "display"]):
            candidate_text_cols.append(col)

    print("\nCandidate Column Mappings:")
    print(f"  - Primary / External ID candidate: {candidate_id_cols}")
    print(f"  - Category / Taxonomic candidate: {candidate_category_cols}")
    print(f"  - Display Name / Title candidate:  {candidate_text_cols}")

    # 6. ID to Image Matching Check
    if "id" in df.columns:
        expected_filenames = df["id"].astype(str) + ".jpg"
        existing_filenames = set(os.listdir(img_location)) if img_location.exists() else set()
        matched = expected_filenames.isin(existing_filenames).sum()
        missing_images = len(df) - matched
        print(f"\nMetadata ID <-> Physical Image Linkage:")
        print(f"  - Matched records with existing image file: {matched:,} / {len(df):,}")
        print(f"  - Metadata records missing image file:     {missing_images:,}")
        print(f"  - Orphaned images in folder without metadata: {len(existing_filenames - set(expected_filenames)):,}")

    print("=" * 70)


if __name__ == "__main__":
    main()
