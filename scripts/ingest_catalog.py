"""Script to ingest catalog images from manifest_2000.csv using CLIP ViT-B-32, store SQLite metadata, and build FAISS index."""

import csv
import json
from pathlib import Path
import sys
from typing import Dict, List
import faiss
import numpy as np

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import initialize_database, upsert_product
from app.services.embedding_service import (
    EMBEDDING_DIMENSION,
    MODEL_NAME,
    PRETRAINED_WEIGHTS,
    EmbeddingService,
)

MANIFEST_PATH = PROJECT_ROOT / "data" / "catalog" / "manifest_2000.csv"
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings" / "clip_vit_b32"
RAW_IMAGES_DIR_FALLBACK = (
    Path(os.getenv("RAW_IMAGES_DIR")).resolve()
    if os.getenv("RAW_IMAGES_DIR")
    else PROJECT_ROOT / "data" / "images"
)
DEFAULT_BATCH_SIZE = 64


def resolve_image_path(rel_image_path: str, filename: str) -> Path:
    """Resolve image path checking project catalog, relative path, or configured images fallback."""
    candidates = [
        PROJECT_ROOT / "data" / "catalog" / rel_image_path,
        PROJECT_ROOT / "data" / "catalog" / "images" / filename,
        PROJECT_ROOT / "data" / "images" / filename,
        RAW_IMAGES_DIR_FALLBACK / filename,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not resolve image file for '{filename}' or '{rel_image_path}'.")


def load_manifest(manifest_path: Path) -> List[Dict[str, str]]:
    """Read manifest CSV file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    entries = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(dict(row))
    return entries


def main() -> None:
    print("Initializing SQLite database...")
    initialize_database()

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading manifest from: {MANIFEST_PATH}")
    manifest_entries = load_manifest(MANIFEST_PATH)
    total_discovered = len(manifest_entries)
    print(f"Discovered {total_discovered} entry(ies) in manifest.")

    print("Loading EmbeddingService (CLIP ViT-B-32)...")
    service = EmbeddingService()

    embeddings_list: List[np.ndarray] = []
    product_ids_list: List[int] = []
    failed_files: List[Dict[str, str]] = []
    successful_count = 0
    failed_count = 0

    batch_size = DEFAULT_BATCH_SIZE
    print(f"Starting batch ingestion (batch_size={batch_size})...")

    for i in range(0, total_discovered, batch_size):
        batch = manifest_entries[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_discovered + batch_size - 1) // batch_size
        print(f"--- Batch {batch_num}/{total_batches} (Items {i+1} to {min(i+batch_size, total_discovered)}) ---")

        for item in batch:
            product_id_str = item.get("product_id", "").strip()
            rel_image_path = item.get("image_path", "").strip()
            filename = item.get("filename", "").strip()
            category = item.get("category", "general").strip()

            try:
                img_file_path = resolve_image_path(rel_image_path, filename)
                embedding = service.generate_image_embedding(img_file_path)

                external_id = product_id_str if product_id_str else filename

                # Upsert into SQLite database
                db_product_id = upsert_product(
                    external_id=external_id,
                    image_path=str(img_file_path),
                    filename=filename,
                    category=category,
                    embedding_dimension=EMBEDDING_DIMENSION,
                )

                embeddings_list.append(embedding)
                product_ids_list.append(db_product_id)
                successful_count += 1

            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                failed_files.append({"file": filename, "error": error_msg})
                print(f"  [FAILED] {filename}: {error_msg}", file=sys.stderr)

        print(f"  Processed {min(i+batch_size, total_discovered)}/{total_discovered} images...")

    if successful_count == 0:
        print("Error: No images were successfully processed.", file=sys.stderr)
        sys.exit(1)

    # 1. Save normalized float32 embeddings matrix
    embeddings_file = EMBEDDINGS_DIR / "catalog_embeddings.npy"
    embeddings_matrix = np.vstack(embeddings_list).astype(np.float32)
    np.save(embeddings_file, embeddings_matrix)
    print(f"\nSaved catalog embeddings shape {embeddings_matrix.shape} to: {embeddings_file}")

    # 2. Save matching int64 product IDs array
    product_ids_file = EMBEDDINGS_DIR / "product_ids.npy"
    product_ids_array = np.array(product_ids_list, dtype=np.int64)
    np.save(product_ids_file, product_ids_array)
    print(f"Saved product IDs shape {product_ids_array.shape} to: {product_ids_file}")

    # 3. Build FAISS index with explicit SQLite product IDs
    print(f"Building FAISS IndexFlatIP(dim={EMBEDDING_DIMENSION}) wrapped in IndexIDMap2...")
    base_index = faiss.IndexFlatIP(EMBEDDING_DIMENSION)
    index = faiss.IndexIDMap2(base_index)

    faiss_embeddings = np.ascontiguousarray(embeddings_matrix)
    faiss_ids = np.ascontiguousarray(product_ids_array)

    index.add_with_ids(faiss_embeddings, faiss_ids)
    index_file = EMBEDDINGS_DIR / "catalog.index"
    faiss.write_index(index, str(index_file))
    print(f"Saved FAISS index ({index.ntotal} vectors) to: {index_file}")

    # 4. Verify reload after save
    print("Testing FAISS index reload from disk...")
    reloaded_index = faiss.read_index(str(index_file))
    print(f"Reload verification successful. Reloaded vector count: {reloaded_index.ntotal}")

    # 5. Generate ingestion report log
    report_data = {
        "total_discovered": total_discovered,
        "images_processed": successful_count,
        "images_skipped": failed_count,
        "embeddings_created": len(embeddings_matrix),
        "db_rows_inserted": successful_count,
        "faiss_vectors_added": index.ntotal,
        "mapping_entries_created": len(product_ids_array),
        "reloaded_vector_count": reloaded_index.ntotal,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "model_name": MODEL_NAME,
        "pretrained_weights": PRETRAINED_WEIGHTS,
        "failed_files": failed_files,
    }

    report_file = EMBEDDINGS_DIR / "ingestion_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print(f"Saved ingestion report log to: {report_file}")
    print("\n" + "=" * 60)
    print("FULL INGESTION PIPELINE REPORT")
    print("=" * 60)
    print(f"  Manifest path:            {MANIFEST_PATH}")
    print(f"  Images processed:         {successful_count}")
    print(f"  Images skipped:           {failed_count}")
    print(f"  Embeddings created:       {len(embeddings_matrix)}")
    print(f"  DB rows inserted:         {successful_count}")
    print(f"  FAISS vectors added:      {index.ntotal}")
    print(f"  Mapping entries created:  {len(product_ids_array)}")
    print(f"  Reloaded vector count:    {reloaded_index.ntotal}")
    print("=" * 60)


if __name__ == "__main__":
    main()
