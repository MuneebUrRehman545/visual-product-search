"""Verification test suite for integration fixes:
1. GET /api/catalog/categories (and all aliases)
2. POST /search (quick-select with catalog_filename, with and without disk image)
3. Catalog images serving with CORP headers, explicit MIME type, and fallback SVG
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from app.main import app

def run_tests():
    client = TestClient(app)
    print("=" * 70)
    print("VERIFYING INTEGRATION FIXES")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # TEST 1: Categories Endpoints & Aliases
    # -------------------------------------------------------------------------
    category_routes = [
        "/api/catalog/categories?limit=8",
        "/catalog/categories?limit=8",
        "/api/v1/catalog/categories?limit=8",
        "/api/v1/vision/categories?limit=8",
        "/api/categories?limit=8",
    ]
    print("\n[TEST 1] Verifying Category Endpoints & Aliases...")
    for route in category_routes:
        res = client.get(route)
        print(f"  GET {route} -> Status: {res.status_code}")
        assert res.status_code == 200, f"Expected 200 for {route}, got {res.status_code}"
        data = res.json()
        assert "categories" in data, f"Expected 'categories' key in response for {route}"
        assert len(data["categories"]) > 0, f"Expected at least 1 category for {route}"
        assert data["categories"][0]["category_name"], "Expected valid category_name"
    print("  -> ALL Category routes returned HTTP 200 with valid categories! [PASS]")

    # -------------------------------------------------------------------------
    # TEST 2: POST /search with quick-select (catalog_filename)
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Verifying POST /search quick-select (catalog_filename)...")
    search_routes = [
        "/search",
        "/api/search",
        "/api/v1/search",
        "/api/v1/vision/search",
    ]
    
    # 2a: Existing sample image
    for s_route in search_routes:
        res = client.post(
            s_route,
            data={"catalog_filename": "10003.jpg", "top_k": 5, "model": "clip"}
        )
        print(f"  POST {s_route} (catalog_filename='10003.jpg', model='clip') -> Status: {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["total_results"] > 0, "Expected search results"
        assert len(data["results"]) == 5, f"Expected 5 results, got {len(data['results'])}"

    # 2b: Quick-select with ResNet model
    res_resnet = client.post(
        "/search",
        data={"catalog_filename": "10003.jpg", "top_k": 5, "model": "resnet"}
    )
    print(f"  POST /search (catalog_filename='10003.jpg', model='resnet') -> Status: {res_resnet.status_code}")
    assert res_resnet.status_code == 200
    assert len(res_resnet.json()["results"]) == 5

    # 2c: Quick-select with filename NOT on disk (tests zero-disk DB vector fallback)
    # 15970.jpg is in the catalog database but let's test a non-existent disk file that is in the DB
    res_db_only = client.post(
        "/search",
        data={"catalog_filename": "15970.jpg", "top_k": 5, "model": "clip"}
    )
    print(f"  POST /search (db-only item '15970.jpg') -> Status: {res_db_only.status_code}")
    assert res_db_only.status_code == 200
    assert len(res_db_only.json()["results"]) == 5

    # 2d: JSON body submission
    res_json = client.post(
        "/search",
        json={"catalog_filename": "10003.jpg", "top_k": 5, "model": "clip"}
    )
    print(f"  POST /search (JSON body payload) -> Status: {res_json.status_code}")
    assert res_json.status_code == 200
    assert len(res_json.json()["results"]) == 5
    print("  -> POST /search quick-select passed all checks! [PASS]")

    # -------------------------------------------------------------------------
    # TEST 3: Catalog Images Serving, CORP, CORS, and SVG Fallback
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Verifying Catalog Images, CORP Headers, and ORB Protection...")
    
    # 3a: Existing image on disk
    img_res = client.get("/catalog-images/10003.jpg")
    print(f"  GET /catalog-images/10003.jpg -> Status: {img_res.status_code}")
    assert img_res.status_code == 200
    assert img_res.headers.get("cross-origin-resource-policy") == "cross-origin", "Missing CORP header!"
    assert "image/" in img_res.headers.get("content-type", ""), f"Unexpected Content-Type: {img_res.headers.get('content-type')}"
    print(f"    Content-Type: {img_res.headers.get('content-type')}")
    print(f"    Cross-Origin-Resource-Policy: {img_res.headers.get('cross-origin-resource-policy')}")
    print(f"    Access-Control-Allow-Origin: {img_res.headers.get('access-control-allow-origin')}")

    # 3b: Preflight OPTIONS on image
    options_res = client.options("/catalog-images/10003.jpg")
    print(f"  OPTIONS /catalog-images/10003.jpg -> Status: {options_res.status_code}")
    assert options_res.status_code == 204
    assert options_res.headers.get("cross-origin-resource-policy") == "cross-origin"

    # 3c: Missing image file on disk (SVG fallback)
    missing_res = client.get("/catalog-images/non_existent_image_999999.jpg")
    print(f"  GET /catalog-images/non_existent_image_999999.jpg (Missing file) -> Status: {missing_res.status_code}")
    assert missing_res.status_code == 200, "Missing image should return 200 SVG fallback to prevent ORB block"
    assert missing_res.headers.get("content-type") == "image/svg+xml"
    assert missing_res.headers.get("cross-origin-resource-policy") == "cross-origin"
    assert b"<svg" in missing_res.content
    print(f"    Fallback Content-Type: {missing_res.headers.get('content-type')}")
    print(f"    Fallback Body begins with: {missing_res.content[:30]}")
    print("  -> Catalog image serving is ORB-proof! [PASS]")

    print("\n" + "=" * 70)
    print("ALL INTEGRATION VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
