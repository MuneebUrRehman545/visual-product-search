"""Script to build and verify ResNet50 FAISS IndexFlatIP index wrapped with IndexIDMap2."""

from pathlib import Path
import sys
import faiss
import numpy as np

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings" / "resnet50"
EMBEDDINGS_FILE = EMBEDDINGS_DIR / "catalog_embeddings.npy"
PRODUCT_IDS_FILE = EMBEDDINGS_DIR / "product_ids.npy"
INDEX_FILE = EMBEDDINGS_DIR / "catalog.index"
EXPECTED_DIMENSION = 2048


def main() -> None:
    print("Loading ResNet50 embeddings and product IDs...")
    if not EMBEDDINGS_FILE.exists():
        print(f"Error: Embeddings file '{EMBEDDINGS_FILE}' not found.", file=sys.stderr)
        sys.exit(1)

    if not PRODUCT_IDS_FILE.exists():
        print(f"Error: Product IDs file '{PRODUCT_IDS_FILE}' not found.", file=sys.stderr)
        sys.exit(1)

    embeddings = np.load(EMBEDDINGS_FILE)
    product_ids = np.load(PRODUCT_IDS_FILE)

    print(f"Loaded embeddings shape: {embeddings.shape}, dtype: {embeddings.dtype}")
    print(f"Loaded product IDs shape: {product_ids.shape}, dtype: {product_ids.dtype}")

    # Validations
    if embeddings.ndim != 2:
        print(f"Error: Expected 2D embeddings array, got shape {embeddings.shape}", file=sys.stderr)
        sys.exit(1)

    if product_ids.ndim != 1:
        print(f"Error: Expected 1D product IDs array, got shape {product_ids.shape}", file=sys.stderr)
        sys.exit(1)

    if embeddings.shape[1] != EXPECTED_DIMENSION:
        print(
            f"Error: Expected embedding dimension {EXPECTED_DIMENSION}, got {embeddings.shape[1]}",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(embeddings) != len(product_ids):
        print(
            f"Error: Mismatched lengths! Embeddings count ({len(embeddings)}) != Product IDs count ({len(product_ids)})",
            file=sys.stderr,
        )
        sys.exit(1)

    if not np.all(np.isfinite(embeddings)):
        print("Error: Embeddings contain non-finite values (NaN or Inf).", file=sys.stderr)
        sys.exit(1)

    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-4):
        print(
            f"Error: Embedding norms are not approximately 1.0 (min: {norms.min():.6f}, max: {norms.max():.6f})",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(set(product_ids)) != len(product_ids):
        print("Error: Duplicate product IDs found in product IDs array.", file=sys.stderr)
        sys.exit(1)

    if len(embeddings) == 0:
        print("Error: No embeddings found to build FAISS index.", file=sys.stderr)
        sys.exit(1)

    # Convert to contiguous float32 and int64 arrays for FAISS
    embeddings = np.ascontiguousarray(embeddings.astype(np.float32))
    product_ids = np.ascontiguousarray(product_ids.astype(np.int64))

    print(f"Building FAISS IndexFlatIP(dim={EXPECTED_DIMENSION}) wrapped in IndexIDMap2...")
    base_index = faiss.IndexFlatIP(EXPECTED_DIMENSION)
    index = faiss.IndexIDMap2(base_index)

    index.add_with_ids(embeddings, product_ids)
    print(f"Added {index.ntotal} vector(s) with product IDs.")

    # Save index
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_FILE))
    print(f"Saved ResNet50 FAISS index to: {INDEX_FILE}")

    # Reload index and verify
    print("Reloading ResNet50 FAISS index to verify vector count...")
    reloaded_index = faiss.read_index(str(INDEX_FILE))

    if reloaded_index.ntotal != len(embeddings):
        print(
            f"Verification Error: Reloaded vector count ({reloaded_index.ntotal}) != expected ({len(embeddings)})",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\nResNet50 FAISS Index Summary:")
    print(f"  Index Path:   {INDEX_FILE}")
    print(f"  Vector Count: {reloaded_index.ntotal}")
    print(f"  Dimension:    {reloaded_index.d}")
    print(f"  Index Type:   IndexIDMap2(IndexFlatIP)")
    print("ResNet50 FAISS index built and verified successfully.")


if __name__ == "__main__":
    main()
