"""Script to verify system integrity for 2,000-image catalog ingestion."""

from pathlib import Path
import sys
from typing import List
import faiss
import numpy as np

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_all_products, get_product_count

EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings" / "clip_vit_b32"
EMBEDDINGS_FILE = EMBEDDINGS_DIR / "catalog_embeddings.npy"
PRODUCT_IDS_FILE = EMBEDDINGS_DIR / "product_ids.npy"
INDEX_FILE = EMBEDDINGS_DIR / "catalog.index"
EXPECTED_COUNT = 2000
EXPECTED_DIMENSION = 512


def main() -> None:
    all_passed = True
    mismatches: List[str] = []

    def check(name: str, condition: bool, details: str = "") -> None:
        nonlocal all_passed
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_passed = False
            mismatches.append(f"{name}: {details}")
        msg = f"[{status}] {name}"
        if details:
            msg += f" - {details}"
        print(msg)

    print("=" * 60)
    print("VERIFYING SYSTEM INTEGRITY (2,000-Image Catalog)")
    print("=" * 60)

    # 1. DB count check
    db_count = -1
    try:
        db_count = get_product_count()
        check("DB count check", db_count == EXPECTED_COUNT, f"Database count = {db_count} (Expected: {EXPECTED_COUNT})")
    except Exception as e:
        check("DB count check", False, f"Database query failed: {e}")

    # 2 & 3. Embeddings & Mapping files check
    embeddings = None
    product_ids = None

    if EMBEDDINGS_FILE.exists():
        try:
            embeddings = np.load(EMBEDDINGS_FILE)
            embed_ok = (embeddings.shape == (EXPECTED_COUNT, EXPECTED_DIMENSION))
            check(
                "Embeddings shape & count check",
                embed_ok,
                f"Shape = {embeddings.shape} (Expected: ({EXPECTED_COUNT}, {EXPECTED_DIMENSION}))",
            )
        except Exception as e:
            check("Embeddings shape & count check", False, f"Failed loading embeddings: {e}")
    else:
        check("Embeddings shape & count check", False, f"File '{EMBEDDINGS_FILE}' missing")

    if PRODUCT_IDS_FILE.exists():
        try:
            product_ids = np.load(PRODUCT_IDS_FILE)
            mapping_ok = (product_ids.shape == (EXPECTED_COUNT,))
            check(
                "Mapping count check",
                mapping_ok,
                f"Mapping count = {len(product_ids)} (Expected: {EXPECTED_COUNT})",
            )
        except Exception as e:
            check("Mapping count check", False, f"Failed loading product IDs: {e}")
    else:
        check("Mapping count check", False, f"File '{PRODUCT_IDS_FILE}' missing")

    # 4. Embeddings valid float32 check
    if embeddings is not None:
        dtype_ok = (embeddings.dtype == np.float32)
        check("Embeddings valid float32 check", dtype_ok, f"Dtype = {embeddings.dtype}")
    else:
        check("Embeddings valid float32 check", False, "Embeddings array not available")

    # 5. No NaN / finite vectors check
    if embeddings is not None:
        finite_ok = bool(np.all(np.isfinite(embeddings)))
        check("No NaN vectors check", finite_ok, "All vector values are finite (no NaN or Inf)")
    else:
        check("No NaN vectors check", False, "Embeddings array not available")

    # 6. FAISS reload & count check
    if INDEX_FILE.exists():
        try:
            reloaded_index = faiss.read_index(str(INDEX_FILE))
            faiss_count = reloaded_index.ntotal
            faiss_ok = (faiss_count == EXPECTED_COUNT)
            check(
                "FAISS reload & vector count check",
                faiss_ok,
                f"Reloaded FAISS count = {faiss_count} (Expected: {EXPECTED_COUNT})",
            )
        except Exception as e:
            check("FAISS reload & vector count check", False, f"FAISS reload failed: {e}")
    else:
        check("FAISS reload & vector count check", False, f"File '{INDEX_FILE}' missing")

    # 7. Image paths valid check
    try:
        db_products = fetch_all_products()
        missing_paths = []
        for prod in db_products:
            img_p = Path(prod["image_path"])
            if not img_p.exists() or not img_p.is_file():
                missing_paths.append(str(img_p))

        paths_ok = (len(missing_paths) == 0 and len(db_products) == EXPECTED_COUNT)
        check(
            "Image paths valid check",
            paths_ok,
            f"{len(db_products) - len(missing_paths)}/{len(db_products)} image paths verified on disk",
        )
    except Exception as e:
        check("Image paths valid check", False, f"Failed image path validation: {e}")

    # Output Summary & Mismatches
    print("\n" + "=" * 60)
    if mismatches:
        print("MISMATCHES DETECTED:")
        for m in mismatches:
            print(f"  - {m}")
        print("=" * 60)
        print("RESULT: SYSTEM INTEGRITY CHECK FAILED.")
        sys.exit(1)
    else:
        print("MISMATCHES DETECTED: None")
        print("=" * 60)
        print("RESULT: SYSTEM INTEGRITY CHECK PASSED SUCCESSFULLY.")
        sys.exit(0)


if __name__ == "__main__":
    main()
