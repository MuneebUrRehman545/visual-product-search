"""Script to compare CLIP vs ResNet visual search results for a single query image."""

import argparse
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.clip_search_service import CLIPSearchService
from app.services.resnet_search_service import ResNetSearchService

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CATALOG_IMAGES_DIR = PROJECT_ROOT / "data" / "catalog" / "images"


def find_default_query_image(directory: Path) -> Path:
    """Find the first supported catalog image to use as default query."""
    if not directory.exists():
        print(f"Error: Catalog directory '{directory}' not found.", file=sys.stderr)
        sys.exit(1)

    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return path

    print(f"Error: No supported images found in '{directory}'.", file=sys.stderr)
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare CLIP vs ResNet visual search on a single query image."
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=None,
        help="Path to query image file (defaults to first catalog image).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of nearest neighbors to retrieve (1-50, default: 5).",
    )
    return parser.parse_args()


def print_results(model_name: str, results: List[Dict[str, Any]], elapsed_seconds: float) -> None:
    """Print formatted search results table."""
    print("=" * 70)
    print(f"RESULTS FOR {model_name} (Search time: {elapsed_seconds * 1000:.2f} ms)")
    print("=" * 70)
    if not results:
        print("No matching products found.\n")
        return

    header = f"{'Rank':<6} {'Product ID':<12} {'Filename':<25} {'Category':<15} {'Score':<10}"
    print(header)
    print("-" * len(header))

    for item in results:
        print(
            f"{item['rank']:<6} "
            f"{item['product_id']:<12} "
            f"{item['filename']:<25} "
            f"{item['category']:<15} "
            f"{item['similarity_score']:<10.6f}"
        )
    print()


def main() -> None:
    args = parse_args()

    if args.image is not None:
        query_image = args.image.resolve()
        if not query_image.exists():
            print(f"Error: Query image file '{query_image}' does not exist.", file=sys.stderr)
            sys.exit(1)
    else:
        query_image = find_default_query_image(CATALOG_IMAGES_DIR)

    print(f"Query Image Path: {query_image}")
    print(f"Top K: {args.top_k}\n")

    print("Initializing search services...")
    clip_service = CLIPSearchService()
    resnet_service = ResNetSearchService()
    print()

    # Execute CLIP search
    start_time = time.perf_counter()
    clip_results = clip_service.search(query_image, top_k=args.top_k)
    clip_elapsed = time.perf_counter() - start_time

    # Execute ResNet search
    start_time = time.perf_counter()
    resnet_results = resnet_service.search(query_image, top_k=args.top_k)
    resnet_elapsed = time.perf_counter() - start_time

    # Print results
    print_results("CLIP (ViT-B-32)", clip_results, clip_elapsed)
    print_results("ResNet-50", resnet_results, resnet_elapsed)


if __name__ == "__main__":
    main()
