"""Script to ingest catalog images using ResNet50 and save embeddings to data/embeddings/resnet50/."""

import json
from pathlib import Path
import sys
from typing import List
import numpy as np

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import initialize_database, upsert_product
from app.services.resnet_embedding_service import (
    EMBEDDING_DIMENSION,
    MODEL_NAME,
    ResNet50EmbeddingService,
)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CATALOG_IMAGES_DIR = PROJECT_ROOT / "data" / "catalog" / "images"
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings" / "resnet50"


def discover_images(catalog_dir: Path) -> List[Path]:
    """Recursively search for supported images in catalog directory sorted deterministically."""
    if not catalog_dir.exists():
        print(f"Warning: Catalog directory '{catalog_dir}' does not exist.", file=sys.stderr)
        return []

    return [
        path
        for path in sorted(catalog_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def main() -> None:
    print("Initializing SQLite database...")
    initialize_database()

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Searching for catalog images in: {CATALOG_IMAGES_DIR}")
    image_paths = discover_images(CATALOG_IMAGES_DIR)
    total_discovered = len(image_paths)
    print(f"Discovered {total_discovered} image(s).")

    print("Loading ResNet50EmbeddingService...")
    service = ResNet50EmbeddingService()

    embeddings_list: List[np.ndarray] = []
    product_ids_list: List[int] = []
    failed_files: List[dict] = []
    successful_count = 0
    failed_count = 0

    for idx, img_path in enumerate(image_paths, 1):
        try:
            rel_path = img_path.relative_to(CATALOG_IMAGES_DIR)
        except ValueError:
            rel_path = img_path

        print(f"[{idx}/{total_discovered}] Processing {rel_path}...", end=" ", flush=True)

        try:
            embedding = service.generate_image_embedding(img_path)

            category = rel_path.parent.name if rel_path.parent != Path(".") else "general"
            external_id = str(rel_path).replace("\\", "/")

            product_id = upsert_product(
                external_id=external_id,
                image_path=str(img_path.resolve()),
                filename=img_path.name,
                category=category,
                embedding_dimension=EMBEDDING_DIMENSION,
            )

            embeddings_list.append(embedding)
            product_ids_list.append(product_id)
            successful_count += 1
            print("OK")

        except Exception as e:
            failed_count += 1
            error_msg = str(e)
            failed_files.append({"file": str(rel_path), "error": error_msg})
            print(f"FAILED ({error_msg})")

    if successful_count == 0:
        print("Error: No images were successfully processed.", file=sys.stderr)
        sys.exit(1)

    # Save embeddings matrix
    embeddings_file = EMBEDDINGS_DIR / "catalog_embeddings.npy"
    embeddings_matrix = np.vstack(embeddings_list).astype(np.float32)
    np.save(embeddings_file, embeddings_matrix)
    print(f"Saved ResNet50 embeddings shape {embeddings_matrix.shape} to: {embeddings_file}")

    # Save product IDs array
    product_ids_file = EMBEDDINGS_DIR / "product_ids.npy"
    product_ids_array = np.array(product_ids_list, dtype=np.int64)
    np.save(product_ids_file, product_ids_array)
    print(f"Saved product IDs shape {product_ids_array.shape} to: {product_ids_file}")

    # Generate ingestion report
    report_data = {
        "total_discovered": total_discovered,
        "successful": successful_count,
        "failed": failed_count,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "model_name": MODEL_NAME,
        "failed_files": failed_files,
    }

    report_file = EMBEDDINGS_DIR / "ingestion_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print(f"Saved ResNet50 ingestion report to: {report_file}")
    print("\nResNet50 Ingestion Summary:")
    print(f"  Total Discovered: {total_discovered}")
    print(f"  Successful: {successful_count}")
    print(f"  Failed: {failed_count}")


if __name__ == "__main__":
    main()
