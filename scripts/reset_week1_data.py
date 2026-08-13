"""Script to safely reset generated Week 1 data (database rows, FAISS indexes, embeddings)."""

from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "catalog.db"

FILES_TO_REMOVE = [
    # Root embeddings folder
    PROJECT_ROOT / "data" / "embeddings" / "catalog_embeddings.npy",
    PROJECT_ROOT / "data" / "embeddings" / "product_ids.npy",
    PROJECT_ROOT / "data" / "embeddings" / "catalog.index",
    PROJECT_ROOT / "data" / "embeddings" / "ingestion_report.json",
    # CLIP folder
    PROJECT_ROOT / "data" / "embeddings" / "clip_vit_b32" / "catalog_embeddings.npy",
    PROJECT_ROOT / "data" / "embeddings" / "clip_vit_b32" / "product_ids.npy",
    PROJECT_ROOT / "data" / "embeddings" / "clip_vit_b32" / "catalog.index",
    PROJECT_ROOT / "data" / "embeddings" / "clip_vit_b32" / "ingestion_report.json",
    # ResNet50 folder
    PROJECT_ROOT / "data" / "embeddings" / "resnet50" / "catalog_embeddings.npy",
    PROJECT_ROOT / "data" / "embeddings" / "resnet50" / "product_ids.npy",
    PROJECT_ROOT / "data" / "embeddings" / "resnet50" / "catalog.index",
    PROJECT_ROOT / "data" / "embeddings" / "resnet50" / "ingestion_report.json",
]


def main() -> None:
    print("=" * 60)
    print("RESETTING GENERATED WEEK 1 DATA")
    print("=" * 60)

    removed_files = []

    # 1. Delete generated embedding files and FAISS indexes
    for file_path in FILES_TO_REMOVE:
        if file_path.exists():
            try:
                file_path.unlink()
                removed_files.append(str(file_path))
                print(f"[REMOVED FILE] {file_path}")
            except Exception as e:
                print(f"[ERROR REMOVING FILE] {file_path}: {e}", file=sys.stderr)

    # 2. Clear product rows from SQLite database
    rows_deleted = 0
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM products;")
            rows_deleted = cursor.rowcount
            conn.commit()
            conn.close()
            print(f"[DATABASE RESET] Cleared {rows_deleted} product rows from {DB_PATH}")
        except Exception as e:
            print(f"[ERROR CLEARING DATABASE] {e}", file=sys.stderr)
    else:
        print(f"[INFO] Database file '{DB_PATH}' does not exist.")

    print("\n" + "=" * 60)
    print("WEEK 1 DATA RESET SUMMARY")
    print("=" * 60)
    print(f"Total files removed: {len(removed_files)}")
    print(f"Total SQLite rows deleted: {rows_deleted}")
    print("\nPreserved (Not Modified):")
    print("  - Application & script source code")
    print("  - Catalog image dataset")
    print("  - 2,000-image manifest (data/catalog/manifest_2000.csv)")
    print("  - Ground truth evaluation files (data/evaluation/)")


if __name__ == "__main__":
    main()
