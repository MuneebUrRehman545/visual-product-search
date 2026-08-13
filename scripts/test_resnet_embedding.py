"""Script to test ResNet50EmbeddingService on a catalog image."""

from pathlib import Path
import sys
import numpy as np

# Resolve project root dynamically using pathlib
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.resnet_embedding_service import ResNet50EmbeddingService

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CATALOG_IMAGES_DIR = PROJECT_ROOT / "data" / "catalog" / "images"
EXPECTED_DIMENSION = 2048


def find_first_image(directory: Path) -> Path:
    """Recursively search for the first valid supported image in directory."""
    if not directory.exists():
        print(f"Error: Catalog directory '{directory}' does not exist.", file=sys.stderr)
        sys.exit(1)

    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return path

    print(
        f"Error: No valid images ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) found in '{directory}'.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    first_image = find_first_image(CATALOG_IMAGES_DIR)
    print(f"Selected image path: {first_image}")

    try:
        service = ResNet50EmbeddingService()
    except Exception as e:
        print(f"Error loading ResNet50EmbeddingService: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Device: {service.device}")

    try:
        embedding = service.generate_image_embedding(first_image)
    except Exception as e:
        print(f"Error generating ResNet50 embedding: {e}", file=sys.stderr)
        sys.exit(1)

    shape = embedding.shape
    dtype = embedding.dtype
    norm = float(np.linalg.norm(embedding))
    first_five = embedding[:5]

    print(f"Embedding shape: {shape}")
    print(f"Embedding dtype: {dtype}")
    print(f"Embedding norm: {norm:.6f}")
    print(f"First five values: {first_five}")

    # Verifications
    if shape != (EXPECTED_DIMENSION,):
        print(
            f"Verification Error: Expected shape ({EXPECTED_DIMENSION},), got {shape}",
            file=sys.stderr,
        )
        sys.exit(1)

    if dtype != np.float32:
        print(f"Verification Error: Expected dtype float32, got {dtype}", file=sys.stderr)
        sys.exit(1)

    if not np.all(np.isfinite(embedding)):
        print(
            "Verification Error: Embedding contains non-finite values (NaN or Inf).",
            file=sys.stderr,
        )
        sys.exit(1)

    if not np.isclose(norm, 1.0, atol=1e-4):
        print(
            f"Verification Error: Expected norm ≈ 1.0 (atol=1e-4), got {norm}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("ResNet50 embedding test passed successfully.")


if __name__ == "__main__":
    main()
