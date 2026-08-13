"""Smoke test script for Week 2 readiness verification."""

from pathlib import Path
import random
import sys

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_all_products
from app.services.clip_search_service import CLIPSearchService


def main() -> None:
    random.seed(42)

    print("=" * 60)
    print("WEEK 2 READINESS SMOKE TEST (5 RANDOM QUERIES)")
    print("=" * 60)

    # 1. Fetch catalog products from database
    products = fetch_all_products()
    if not products:
        print("Error: No products found in database.", file=sys.stderr)
        sys.exit(1)

    # Pick 5 random products for query test
    sample_size = min(5, len(products))
    test_products = random.sample(products, sample_size)

    print(f"Loaded {len(products)} products from SQLite database.")
    print(f"Selected {sample_size} random query images.\n")

    # 2. Initialize CLIPSearchService
    try:
        search_service = CLIPSearchService()
    except Exception as e:
        print(f"Error initializing CLIPSearchService: {e}", file=sys.stderr)
        sys.exit(1)

    all_passed = True

    # 3. Execute search test per image
    for idx, prod in enumerate(test_products, start=1):
        query_image_path = Path(prod["image_path"])
        expected_product_id = prod["id"]

        if not query_image_path.exists():
            print(f"[{idx}/5] FAILED: Image file '{query_image_path}' not found.", file=sys.stderr)
            all_passed = False
            continue

        try:
            results = search_service.search(query_image_path, top_k=5)
        except Exception as e:
            print(f"[{idx}/5] FAILED: Search execution error: {e}", file=sys.stderr)
            all_passed = False
            continue

        if not results:
            print(f"[{idx}/5] FAILED: No search results returned.", file=sys.stderr)
            all_passed = False
            continue

        top_result = results[0]
        top_product_id = top_result["product_id"]
        top_filename = top_result["filename"]
        similarity_score = top_result["similarity_score"]

        is_correct = (top_product_id == expected_product_id)
        if not is_correct:
            all_passed = False

        status = "PASS" if is_correct else "FAIL"

        print(f"Query {idx}:")
        print(f"  query image:      {query_image_path.name}")
        print(f"  top result:       {top_filename} (Product ID: {top_product_id})")
        print(f"  similarity score: {similarity_score:.6f}")
        print(f"  status:           [{status}] (Expected Product ID: {expected_product_id})\n")

    print("=" * 60)
    if all_passed:
        print("RESULT: SMOKE TEST PASSED (All 5 queries verified top-1 correct).")
        sys.exit(0)
    else:
        print("RESULT: SMOKE TEST FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
