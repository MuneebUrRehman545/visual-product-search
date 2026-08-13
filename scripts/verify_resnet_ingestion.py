"""Script to verify ResNet50 catalog ingestion completeness and dataset integrity."""

from pathlib import Path
import sys
from typing import Set
import faiss
import numpy as np

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_all_products, get_product_count

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CATALOG_IMAGES_DIR = PROJECT_ROOT / "data" / "catalog" / "images"
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings" / "resnet50"
EMBEDDINGS_FILE = EMBEDDINGS_DIR / "catalog_embeddings.npy"
PRODUCT_IDS_FILE = EMBEDDINGS_DIR / "product_ids.npy"
INDEX_FILE = EMBEDDINGS_DIR / "catalog.index"
EXPECTED_DIMENSION = 2048


def main() -> None:
    all_passed = True

    def check(name: str, condition: bool, details: str = "") -> None:
        nonlocal all_passed
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_passed = False
        msg = f"[{status}] {name}"
        if details:
            msg += f" - {details}"
        print(msg)

    # 1. Catalog images exist
    if CATALOG_IMAGES_DIR.exists():
        images = [
            p for p in CATALOG_IMAGES_DIR.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        image_count = len(images)
        check("Catalog images exist check", image_count > 0, f"Found {image_count} catalog image(s)")
    else:
        image_count = 0
        check("Catalog images exist check", False, f"Directory '{CATALOG_IMAGES_DIR}' missing")

    # 2. SQLite product rows exist
    try:
        db_count = get_product_count()
        check("SQLite product rows exist check", db_count > 0, f"Found {db_count} product row(s)")
    except Exception as e:
        db_count = -1
        check("SQLite product rows exist check", False, f"Database query failed: {e}")

    # 3. ResNet embeddings file exists
    embeddings_file_exists = EMBEDDINGS_FILE.exists()
    check("ResNet embeddings file exists check", embeddings_file_exists, f"File: {EMBEDDINGS_FILE}")

    # 4. ResNet product IDs file exists
    product_ids_file_exists = PRODUCT_IDS_FILE.exists()
    check("ResNet product IDs file exists check", product_ids_file_exists, f"File: {PRODUCT_IDS_FILE}")

    # 5. ResNet FAISS index exists
    index_file_exists = INDEX_FILE.exists()
    check("ResNet FAISS index file exists check", index_file_exists, f"File: {INDEX_FILE}")

    embeddings = None
    product_ids = None
    reloaded_index = None

    if embeddings_file_exists:
        try:
            embeddings = np.load(EMBEDDINGS_FILE)
        except Exception as e:
            check("Embedding array loading", False, f"Failed to load: {e}")

    if product_ids_file_exists:
        try:
            product_ids = np.load(PRODUCT_IDS_FILE)
        except Exception as e:
            check("Product ID array loading", False, f"Failed to load: {e}")

    if index_file_exists:
        try:
            reloaded_index = faiss.read_index(str(INDEX_FILE))
        except Exception as e:
            check("FAISS index loading", False, f"Failed to load: {e}")

    # 6. Embedding shape is N x 2048
    if embeddings is not None:
        shape_ok = (embeddings.ndim == 2 and embeddings.shape[1] == EXPECTED_DIMENSION)
        check("Embedding shape N x 2048 check", shape_ok, f"Shape = {embeddings.shape}")
    else:
        check("Embedding shape N x 2048 check", False, "Embeddings array not loaded")

    # 7. Embedding dtype is float32
    if embeddings is not None:
        dtype_ok = (embeddings.dtype == np.float32)
        check("Embedding dtype float32 check", dtype_ok, f"Dtype = {embeddings.dtype}")
    else:
        check("Embedding dtype float32 check", False, "Embeddings array not loaded")

    # 8. Product ID dtype is int64
    if product_ids is not None:
        id_dtype_ok = (product_ids.dtype == np.int64)
        check("Product ID dtype int64 check", id_dtype_ok, f"Dtype = {product_ids.dtype}")
    else:
        check("Product ID dtype int64 check", False, "Product IDs array not loaded")

    # 9. Values are finite
    if embeddings is not None:
        finite_ok = bool(np.all(np.isfinite(embeddings)))
        check("Finite values check", finite_ok, "All embedding values are finite (no NaN/Inf)")
    else:
        check("Finite values check", False, "Embeddings array not loaded")

    # 10. Embedding norms are approximately 1.0
    if embeddings is not None and embeddings.size > 0:
        norms = np.linalg.norm(embeddings, axis=1)
        norms_ok = bool(np.allclose(norms, 1.0, atol=1e-4))
        check("Embedding norms check", norms_ok, f"Min norm: {norms.min():.6f}, Max norm: {norms.max():.6f}")
    else:
        check("Embedding norms check", False, "Embeddings array not loaded")

    # 11. Product IDs are unique
    if product_ids is not None and product_ids.size > 0:
        unique_ok = (len(set(product_ids)) == len(product_ids))
        check("Product IDs unique check", unique_ok, f"Total IDs = {len(product_ids)}, Unique = {len(set(product_ids))}")
    else:
        check("Product IDs unique check", False, "Product IDs array not loaded")

    # 12. Product ID count equals embedding row count
    if embeddings is not None and product_ids is not None:
        count_match = (len(product_ids) == len(embeddings))
        check("Product ID count equals embedding row count check", count_match, f"IDs count = {len(product_ids)}, Embeddings count = {len(embeddings)}")
    else:
        check("Product ID count equals embedding row count check", False, "Arrays not loaded")

    # 13. FAISS vector count equals embedding row count
    if reloaded_index is not None and embeddings is not None:
        faiss_match = (reloaded_index.ntotal == len(embeddings))
        check("FAISS vector count equals embedding row count check", faiss_match, f"FAISS count = {reloaded_index.ntotal}, Embeddings count = {len(embeddings)}")
    else:
        check("FAISS vector count equals embedding row count check", False, "Index or embeddings not loaded")

    # 14. Every product ID exists in SQLite
    if product_ids is not None and product_ids.size > 0:
        try:
            db_products = fetch_all_products()
            db_ids: Set[int] = {row["id"] for row in db_products}
            missing_ids = [pid for pid in product_ids if pid not in db_ids]
            all_exist = (len(missing_ids) == 0)
            check(
                "Every product ID exists in SQLite check",
                all_exist,
                f"{len(product_ids) - len(missing_ids)}/{len(product_ids)} IDs present in database",
            )
        except Exception as e:
            check("Every product ID exists in SQLite check", False, f"Database query error: {e}")
    else:
        check("Every product ID exists in SQLite check", False, "Product IDs array not loaded")

    print("\n----------------------------------------")
    if all_passed:
        print("RESULT: ALL RESNET50 INGESTION CHECKS PASSED SUCCESSFULLY.")
        sys.exit(0)
    else:
        print("RESULT: ONE OR MORE RESNET50 INGESTION CHECKS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
