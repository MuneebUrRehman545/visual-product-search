"""Verification script for Week 2 visual search API endpoint gate."""

from pathlib import Path
import sqlite3
import sys

from fastapi.testclient import TestClient

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import get_connection
from app.main import app


def verify_product_id_in_db(product_id: int) -> bool:
    """Verify that a product ID exists in SQLite catalog database."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE id = ?;", (product_id,))
        count = cursor.fetchone()[0]
        return count > 0


def main() -> None:
    client = TestClient(app)

    print("=" * 80)
    print("BACKEND VISUAL SEARCH API GATE VERIFICATION SUITE")
    print("=" * 80)

    test_results = {}

    # ----------------------------------------------------
    # TEST 1: GET /health
    # ----------------------------------------------------
    print("\n--- [TEST 1] GET /health ---")
    h_res = client.get("/health")
    h_ok = (h_res.status_code == 200 and h_res.json() == {"status": "ok"})
    test_results["1. GET /health"] = "PASS" if h_ok else "FAIL"
    print(f"Status Code: {h_res.status_code}")
    print(f"Payload:     {h_res.json()}")
    print(f"Result:      [{test_results['1. GET /health']}]")

    # Load test image 15025.jpg
    img_path_15025 = PROJECT_ROOT / "data" / "catalog" / "images" / "15025.jpg"
    with open(img_path_15025, "rb") as f:
        img_bytes_15025 = f.read()

    # Load test image 17888.jpg
    img_path_17888 = PROJECT_ROOT / "data" / "catalog" / "images" / "17888.jpg"
    with open(img_path_17888, "rb") as f:
        img_bytes_17888 = f.read()

    # ----------------------------------------------------
    # TEST 2: Valid JPG Search (top_k = 5)
    # ----------------------------------------------------
    print("\n--- [TEST 2] Valid Search: 15025.jpg (top_k=5) ---")
    res_5 = client.post(
        "/api/v1/search",
        files={"file": ("15025.jpg", img_bytes_15025, "image/jpeg")},
        data={"top_k": 5},
    )
    t2_passed = True
    print(f"HTTP Status Code: {res_5.status_code}")

    if res_5.status_code == 200:
        data = res_5.json()
        print(f"Query Filename:   {data['query_filename']}")
        print(f"Total Results:    {data['total_results']}")

        # Assertions
        if data["total_results"] != 5:
            print(f"FAIL Assertion: total_results ({data['total_results']}) != top_k (5)")
            t2_passed = False

        prev_score = 1.000001
        for idx, item in enumerate(data["results"], start=1):
            rank = item["rank"]
            pid = item["product_id"]
            ext_id = item["external_id"]
            score = item["similarity_score"]
            img_url = item["image_url"]

            # Verify image URL returns 200
            img_res = client.get(img_url)
            img_status = img_res.status_code

            print(f"  Rank {rank}: product_id={pid} | external_id={ext_id} | score={score:.6f} | image_url={img_url} [HTTP {img_status}]")

            # Check sequential rank
            if rank != idx:
                print(f"FAIL Assertion: rank ({rank}) != expected ({idx})")
                t2_passed = False

            # Check score ordering (highest to lowest)
            if score > prev_score:
                print(f"FAIL Assertion: score ({score}) > previous ({prev_score})")
                t2_passed = False
            prev_score = score

            # Check DB existence
            if not verify_product_id_in_db(pid):
                print(f"FAIL Assertion: product_id {pid} does not exist in SQLite DB")
                t2_passed = False

            # Check image URL status
            if img_status != 200:
                print(f"FAIL Assertion: image_url {img_url} returned HTTP {img_status}")
                t2_passed = False

        # Rank 1 exact match verification
        top_ext_id = data["results"][0]["external_id"]
        if top_ext_id != "15025":
            print(f"FAIL Assertion: top-1 external_id ({top_ext_id}) != '15025'")
            t2_passed = False
    else:
        t2_passed = False

    test_results["2. Valid JPG (top_k=5)"] = "PASS" if t2_passed else "FAIL"

    # ----------------------------------------------------
    # TEST 3: Valid JPG Search (top_k = 10)
    # ----------------------------------------------------
    print("\n--- [TEST 3] Valid Search: 17888.jpg (top_k=10) ---")
    res_10 = client.post(
        "/api/v1/search",
        files={"file": ("17888.jpg", img_bytes_17888, "image/jpeg")},
        data={"top_k": 10},
    )
    t3_passed = True
    print(f"HTTP Status Code: {res_10.status_code}")

    if res_10.status_code == 200:
        data = res_10.json()
        print(f"Query Filename:   {data['query_filename']}")
        print(f"Total Results:    {data['total_results']}")

        if data["total_results"] != 10:
            print(f"FAIL Assertion: total_results ({data['total_results']}) != top_k (10)")
            t3_passed = False

        prev_score = 1.000001
        for idx, item in enumerate(data["results"], start=1):
            rank = item["rank"]
            pid = item["product_id"]
            ext_id = item["external_id"]
            score = item["similarity_score"]
            img_url = item["image_url"]

            img_res = client.get(img_url)
            img_status = img_res.status_code

            print(f"  Rank {rank}: product_id={pid} | external_id={ext_id} | score={score:.6f} | image_url={img_url} [HTTP {img_status}]")

            if rank != idx:
                print(f"FAIL Assertion: rank ({rank}) != expected ({idx})")
                t3_passed = False

            if score > prev_score:
                print(f"FAIL Assertion: score ({score}) > previous ({prev_score})")
                t3_passed = False
            prev_score = score

            if not verify_product_id_in_db(pid):
                print(f"FAIL Assertion: product_id {pid} does not exist in SQLite DB")
                t3_passed = False

            if img_status != 200:
                print(f"FAIL Assertion: image_url {img_url} returned HTTP {img_status}")
                t3_passed = False

        top_ext_id = data["results"][0]["external_id"]
        if top_ext_id != "17888":
            print(f"FAIL Assertion: top-1 external_id ({top_ext_id}) != '17888'")
            t3_passed = False
    else:
        t3_passed = False

    test_results["3. Valid JPG (top_k=10)"] = "PASS" if t3_passed else "FAIL"

    # ----------------------------------------------------
    # TEST 4: Invalid Text File
    # ----------------------------------------------------
    print("\n--- [TEST 4] Invalid Text File ---")
    txt_res = client.post(
        "/api/v1/search",
        files={"file": ("sample.txt", b"plain text data", "text/plain")},
        data={"top_k": 5},
    )
    t4_passed = (txt_res.status_code == 400)
    print(f"Status Code: {txt_res.status_code}")
    print(f"Payload:     {txt_res.json()}")
    test_results["4. Invalid text file"] = "PASS" if t4_passed else "FAIL"

    # ----------------------------------------------------
    # TEST 5: Corrupted Image
    # ----------------------------------------------------
    print("\n--- [TEST 5] Corrupted Image ---")
    corrupt_res = client.post(
        "/api/v1/search",
        files={"file": ("corrupt.jpg", b"BAD_HEADER_BYTES_1234567890", "image/jpeg")},
        data={"top_k": 5},
    )
    t5_passed = (corrupt_res.status_code == 400)
    print(f"Status Code: {corrupt_res.status_code}")
    print(f"Payload:     {corrupt_res.json()}")
    test_results["5. Corrupted image"] = "PASS" if t5_passed else "FAIL"

    # ----------------------------------------------------
    # TEST 6: Invalid top_k=0
    # ----------------------------------------------------
    print("\n--- [TEST 6] Invalid top_k=0 ---")
    tk0_res = client.post(
        "/api/v1/search",
        files={"file": ("15025.jpg", img_bytes_15025, "image/jpeg")},
        data={"top_k": 0},
    )
    t6_passed = (tk0_res.status_code == 400)
    print(f"Status Code: {tk0_res.status_code}")
    print(f"Payload:     {tk0_res.json()}")
    test_results["6. top_k=0"] = "PASS" if t6_passed else "FAIL"

    # ----------------------------------------------------
    # TEST 7: Invalid top_k=51
    # ----------------------------------------------------
    print("\n--- [TEST 7] Invalid top_k=51 ---")
    tk51_res = client.post(
        "/api/v1/search",
        files={"file": ("15025.jpg", img_bytes_15025, "image/jpeg")},
        data={"top_k": 51},
    )
    t7_passed = (tk51_res.status_code == 400)
    print(f"Status Code: {tk51_res.status_code}")
    print(f"Payload:     {tk51_res.json()}")
    test_results["7. top_k=51"] = "PASS" if t7_passed else "FAIL"

    # ----------------------------------------------------
    # FINAL SUMMARY REPORT
    # ----------------------------------------------------
    print("\n" + "=" * 80)
    print("BACKEND SEARCH API VERIFICATION TEST RESULTS SUMMARY")
    print("=" * 80)
    all_passed = True
    for test_name, status in test_results.items():
        print(f"  {test_name:<35} : [{status}]")
        if status != "PASS":
            all_passed = False
    print("=" * 80)

    if all_passed:
        print("RESULT: BACKEND SEARCH API GATE PASSED SUCCESSFULLY.")
        sys.exit(0)
    else:
        print("RESULT: BACKEND SEARCH API GATE FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
