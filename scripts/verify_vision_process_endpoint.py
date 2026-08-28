"""Verification suite for Week 4 Vision integration contract and endpoints.

Distinguishes:
1. Local Functional & Contract Tests (Validates specific HTTP 400 on bad inputs and HTTP 503 on unconfigured DB)
2. Standalone Search Regression Tests (Proves zero disruption to /search and /api/v1/search without shared DB)
3. Live Shared-Database Integration Tests (Only executed when SHARED_DATABASE_URL is provided)
"""

import io
import json
import os
from pathlib import Path
import sys
import uuid

# Ensure root directory in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.db.shared_database import (
    get_shared_connection,
    is_shared_db_configured,
)
from app.schemas.vision_pipeline import VisionProcessResponse


def create_dummy_image_bytes(format="JPEG", color="blue") -> bytes:
    """Generate in-memory test image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (64, 64), color=color)
    img.save(buf, format=format)
    return buf.getvalue()


def run_tests():
    print("=" * 75)
    print("WEEK 4 DAY 2: VISION INTEGRATION TEST SUITE (PHASE 5D)")
    print("=" * 75)

    client = TestClient(app)
    test_img = create_dummy_image_bytes(format="JPEG", color="blue")
    valid_uuid = str(uuid.uuid4())

    passed = 0
    total = 0

    # ========================================================================
    # SECTION A: LOCAL INPUT VALIDATION & CONTRACT ENFORCEMENT TESTS
    # ========================================================================
    print("\n--- [SECTION A: LOCAL INPUT VALIDATION & CONTRACT ENFORCEMENT] ---")

    # Test 1: Malformed UUID format must return HTTP 400
    total += 1
    print(f"\n[Test {total}] Validating malformed pipeline_run_id format...")
    resp = client.post(
        "/api/v1/vision/process",
        data={"pipeline_run_id": "not-a-valid-uuid", "top_k": "5", "model": "clip"},
        files={"image": ("test.jpg", test_img, "image/jpeg")},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert "pipeline_run_id must be a valid UUID" in resp.json()["detail"]
    print("  -> Passed: Returned HTTP 400 with 'pipeline_run_id must be a valid UUID'")
    passed += 1

    # Test 2: Invalid top_k validation (<1 or >50) must return HTTP 400
    total += 1
    print(f"\n[Test {total}] Validating out-of-range top_k (>50)...")
    resp = client.post(
        "/api/v1/vision/process",
        data={"pipeline_run_id": valid_uuid, "top_k": "100", "model": "clip"},
        files={"image": ("test.jpg", test_img, "image/jpeg")},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert "top_k must be an integer between 1 and 50" in resp.json()["detail"]
    print("  -> Passed: Returned HTTP 400 with 'top_k must be an integer between 1 and 50'")
    passed += 1

    # Test 3: Invalid canonical model choice must return HTTP 400
    total += 1
    print(f"\n[Test {total}] Validating unsupported model parameter...")
    resp = client.post(
        "/api/v1/vision/process",
        data={"pipeline_run_id": valid_uuid, "top_k": "5", "model": "bert_vit"},
        files={"image": ("test.jpg", test_img, "image/jpeg")},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert "Unsupported model" in resp.json()["detail"]
    print("  -> Passed: Returned HTTP 400 with 'Unsupported model'")
    passed += 1

    # Test 4: Corrupt / empty image upload must return HTTP 400
    total += 1
    print(f"\n[Test {total}] Validating corrupt image upload...")
    resp = client.post(
        "/api/v1/vision/process",
        data={"pipeline_run_id": valid_uuid, "top_k": "5", "model": "clip"},
        files={"image": ("bad.jpg", b"corrupt bytes header", "image/jpeg")},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert "Uploaded file is not a valid or supported image" in resp.json()["detail"]
    print("  -> Passed: Returned HTTP 400 with 'Uploaded file is not a valid or supported image'")
    passed += 1

    # Test 5: Fully valid request with unconfigured SHARED_DATABASE_URL must return HTTP 503
    if not is_shared_db_configured():
        total += 1
        print(f"\n[Test {total}] Enforcing strict DB requirement on otherwise valid request (HTTP 503)...")
        resp = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": valid_uuid, "top_k": "5", "model": "clip"},
            files={"image": ("test.jpg", test_img, "image/jpeg")},
        )
        assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
        assert "Shared integration database is not configured" in resp.json()["detail"]
        print("  -> Passed: Returned HTTP 503 Service Unavailable with 'Shared integration database is not configured'")
        passed += 1
    else:
        print("\n[Notice] SHARED_DATABASE_URL is set in environment; skipping unconfigured 503 check.")

    # ========================================================================
    # SECTION B: STANDALONE SEARCH REGRESSION (BACKWARD COMPATIBILITY)
    # ========================================================================
    print("\n--- [SECTION B: STANDALONE SEARCH REGRESSION (BACKWARD COMPATIBILITY)] ---")

    # Test 6: Existing /api/v1/search endpoint with OpenCLIP
    total += 1
    print(f"\n[Test {total}] Regression test: Existing POST /api/v1/search (OpenCLIP)...")
    resp = client.post(
        "/api/v1/search",
        data={"top_k": "4", "model": "clip"},
        files={"file": ("query.jpg", test_img, "image/jpeg")},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    search_data = resp.json()
    assert "results" in search_data
    assert len(search_data["results"]) == 4
    assert search_data["model_used"] == "OpenCLIP_ViT_B_32"
    print(f"  -> Passed: /api/v1/search returned {len(search_data['results'])} results (100% backward compatible)")
    passed += 1

    # Test 7: Existing legacy POST /search endpoint with ResNet-50
    total += 1
    print(f"\n[Test {total}] Regression test: Existing POST /search (ResNet-50)...")
    resp = client.post(
        "/search",
        data={"top_k": "3", "model": "resnet"},
        files={"file": ("query.jpg", test_img, "image/jpeg")},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    search_data = resp.json()
    assert "results" in search_data
    assert len(search_data["results"]) == 3
    assert search_data["model_used"] == "ResNet_50"
    print(f"  -> Passed: /search returned {len(search_data['results'])} results with ResNet-50 (100% backward compatible)")
    passed += 1

    # ========================================================================
    # SECTION C: LIVE SHARED-DATABASE INTEGRATION
    # ========================================================================
    print("\n--- [SECTION C: LIVE SHARED-DATABASE INTEGRATION] ---")

    if is_shared_db_configured():
        print("SHARED_DATABASE_URL detected. Executing live Supabase integration tests...")
        live_run_id = str(uuid.uuid4())

        try:
            # 1. Seed temporary pipeline_runs row
            with get_shared_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO pipeline_runs (id, status, created_at, updated_at) VALUES (%s, 'created', NOW(), NOW());",
                        (live_run_id,),
                    )

            # 2. Execute POST /api/v1/vision/process
            total += 1
            print(f"\n[Test {total}] Executing live /api/v1/vision/process with valid pipeline_run_id...")
            resp = client.post(
                "/api/v1/vision/process",
                data={"pipeline_run_id": live_run_id, "top_k": "5", "model": "clip"},
                files={"image": ("query.jpg", test_img, "image/jpeg")},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            validated = VisionProcessResponse.model_validate(data)
            assert validated.pipeline_run_id == live_run_id
            assert validated.status == "completed"
            assert len(validated.matches) == 5
            extracted_id = validated.extracted_data_id
            print(f"  -> Endpoint returned 200 OK, extracted_data_id = {extracted_id}")

            # 3. Assert row in extracted_data
            with get_shared_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, module, model, confidence FROM extracted_data WHERE id = %s;",
                        (extracted_id,),
                    )
                    row = cur.fetchone()
                    assert row is not None, f"Row with id {extracted_id} not found in extracted_data table"
                    assert row[1] == "vision"
                    assert row[2] == "OpenCLIP_ViT_B_32"
                    print("  -> Verified: Real row persisted in Supabase extracted_data table")

                    # 4. Assert assets row
                    cur.execute(
                        "SELECT id, filename, mime_type FROM assets WHERE pipeline_run_id = %s;",
                        (live_run_id,),
                    )
                    asset_row = cur.fetchone()
                    assert asset_row is not None, "Asset row not found in assets table"
                    print("  -> Verified: Real row persisted in Supabase assets table")

                    # 5. Assert module_events rows
                    cur.execute(
                        "SELECT event, message FROM module_events WHERE pipeline_run_id = %s ORDER BY created_at ASC;",
                        (live_run_id,),
                    )
                    event_rows = cur.fetchall()
                    events = [r[0] for r in event_rows]
                    assert "started" in events, "Missing 'started' module_event"
                    assert "completed" in events, "Missing 'completed' module_event"
                    print(f"  -> Verified: Real module_events persisted ({', '.join(events)})")

            passed += 1

        finally:
            # Clean up test pipeline run (cascades to assets, extracted_data, module_events)
            with get_shared_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM pipeline_runs WHERE id = %s;", (live_run_id,))
            print(f"  -> Cleaned up temporary test pipeline run {live_run_id}")

    else:
        print("[Notice] Live shared-database integration test is SKIPPED because SHARED_DATABASE_URL is not configured in this environment.")
        print("  -> To run live tests, set SHARED_DATABASE_URL in .env and rerun this script.")

    print("\n" + "=" * 75)
    print(f"SUMMARY: All {passed}/{total} executed tests passed successfully!")
    print("=" * 75)


if __name__ == "__main__":
    run_tests()
