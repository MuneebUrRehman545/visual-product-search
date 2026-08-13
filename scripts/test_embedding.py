"""Script to test EmbeddingService on a catalog image."""

from pathlib import Path
import sys
import numpy as np

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embedding_service import EmbeddingService

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CATALOG_IMAGES_DIR = PROJECT_ROOT / "data" / "catalog" / "images"


def find_first_image(directory: Path) -> Path:
    """Recursively search for the first supported image file in the directory."""
    if not directory.exists():
        print(f"Error: Catalog directory '{directory}' does not exist.", file=sys.stderr)
        sys.exit(1)

    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return path

    print(
        f"Error: No supported images ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) found in '{directory}'.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    first_image = find_first_image(CATALOG_IMAGES_DIR)
    print(f"Selected image: {first_image}")

    try:
        service = EmbeddingService()
    except Exception as e:
        print(f"Error initializing EmbeddingService: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Device: {service.device}")

    try:
        embedding = service.generate_image_embedding(first_image)
    except Exception as e:
        print(f"Error generating embedding: {e}", file=sys.stderr)
        sys.exit(1)

    shape = embedding.shape
    dtype = embedding.dtype
    norm = float(np.linalg.norm(embedding))
    first_five = embedding[:5]

    print(f"Shape: {shape}")
    print(f"Dtype: {dtype}")
    print(f"Norm: {norm:.6f}")
    print(f"First five values: {first_five}")

    if shape != (512,):
        print(f"Verification Error: Expected shape (512,), got {shape}", file=sys.stderr)
        sys.exit(1)

    if dtype != np.float32:
        print(f"Verification Error: Expected dtype float32, got {dtype}", file=sys.stderr)
        sys.exit(1)

    if not np.all(np.isfinite(embedding)):
        print("Verification Error: Embedding contains non-finite values (NaN or Inf).", file=sys.stderr)
        sys.exit(1)

    if not np.isclose(norm, 1.0, atol=1e-4):
        print(f"Verification Error: Expected norm ≈ 1.0, got {norm}", file=sys.stderr)
        sys.exit(1)

    print("Embedding test passed successfully.")


if __name__ == "__main__":
    main()
