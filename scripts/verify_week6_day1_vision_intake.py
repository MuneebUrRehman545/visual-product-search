"""Week 6 Day 1: Vision / Intake Module Verification against Unified Integration Contract.

Runs the CURRENT unified upload/intake flow using a REAL image from the catalog
and performs comprehensive field-by-field verification against the frozen contract.
"""

import io
import json
import os
import sys
from pathlib import Path
import uuid
from typing import Any, Dict

# Force offline mode to avoid HF Hub remote ping delays
os.environ["HF_HUB_OFFLINE"] = "1"

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.db.database import get_catalog_item
from app.db.shared_database import (
    check_pipeline_run_exists,
    get_assets_by_run_id,
    get_extracted_data_by_run_id,
    get_module_events_by_run_id,
    get_pipeline_run,
    get_shared_connection,
    is_shared_db_configured,
)
from app.schemas.gateway import GatewayRunDetailResponse, GatewayRunResponse
from app.schemas.vision_pipeline import VisionMatchItem, VisionProcessResponse

# 15 mandatory fields per match in the contract
REQUIRED_MATCH_FIELDS = {
    "rank": int,
    "catalog_item_id": int,
    "product_id": int,
    "external_id": (str, type(None)),
    "filename": str,
    "product_display_name": (str, type(None)),
    "category": (str, type(None)),
    "sub_category": (str, type(None)),
    "article_type": (str, type(None)),
    "base_colour": (str, type(None)),
    "gender": (str, type(None)),
    "season": (str, type(None)),
    "usage": (str, type(None)),
    "image_url": str,
    "similarity_score": (float, int),
}

# Forbidden / legacy fields
FORBIDDEN_FIELDS = {"producer", "match_status", "error"}


def seed_orchestrator_run(run_id: str, status: str = "processing"):
    """Simulate the orchestrator registering an active pipeline run in shared DB."""
    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_runs (id, status, created_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, updated_at = NOW();
                """,
                (run_id, status),
            )


def cleanup_pipeline_runs(run_ids: list):
    """Clean up test pipeline runs from shared database."""
    if not run_ids:
        return
    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            for r_id in run_ids:
                cur.execute("DELETE FROM pipeline_runs WHERE id = %s;", (str(r_id),))


def run_verification():
    print("=" * 80)
    print("WEEK 6 DAY 1: VISION / INTAKE MODULE CONTRACT VERIFICATION")
    print("=" * 80)

    # 1. Image Check
    real_image_path = PROJECT_ROOT / "data" / "sample_images" / "10003.jpg"
    assert real_image_path.exists(), f"Real sample image missing at {real_image_path}"
    with open(real_image_path, "rb") as f:
        real_image_bytes = f.read()

    print(f"\n[Test Image] Using REAL image: {real_image_path.name} ({len(real_image_bytes)} bytes)")
    
    # Verify it is decodable
    pil_img = Image.open(io.BytesIO(real_image_bytes))
    print(f"  -> PIL Dimensions: {pil_img.size}, Format: {pil_img.format}, Mode: {pil_img.mode}")

    client = TestClient(app)
    run_ids_to_clean = []
    
    results_summary = {
        "tests_passed": 0,
        "tests_total": 0,
        "issues": [],
    }

    try:
        # ====================================================================
        # PART 1: TEST POST /api/v1/vision/process (Canonical Frozen Contract)
        # ====================================================================
        print("\n" + "-" * 70)
        print("PART 1: Testing POST /api/v1/vision/process (Canonical Contract Flow)")
        print("-" * 70)

        run_id_1 = str(uuid.uuid4())
        run_ids_to_clean.append(run_id_1)
        seed_orchestrator_run(run_id_1, status="processing")
        print(f"Seeded orchestrator pipeline run: {run_id_1}")

        results_summary["tests_total"] += 1
        resp = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": run_id_1, "top_k": "5", "model": "clip"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        payload_1 = resp.json()
        print("  -> Status: HTTP 200 OK")
        results_summary["tests_passed"] += 1

        # Validate against Pydantic schema
        results_summary["tests_total"] += 1
        pydantic_obj_1 = VisionProcessResponse.model_validate(payload_1)
        print("  -> Successfully validated payload against VisionProcessResponse schema")
        results_summary["tests_passed"] += 1

        # Verify Top-Level Fields
        results_summary["tests_total"] += 1
        assert payload_1["pipeline_run_id"] == run_id_1, f"pipeline_run_id mismatch: {payload_1['pipeline_run_id']} != {run_id_1}"
        assert payload_1["status"] == "completed", f"Status mismatch: {payload_1['status']} != 'completed'"
        assert isinstance(payload_1["confidence"], (float, int)), f"Confidence type invalid: {type(payload_1['confidence'])}"
        assert -1.0 <= payload_1["confidence"] <= 1.0, f"Confidence score {payload_1['confidence']} not in range [-1.0, 1.0]"
        assert "extracted_data_id" in payload_1 and payload_1["extracted_data_id"], "Missing extracted_data_id"
        uuid.UUID(payload_1["extracted_data_id"]) # ensure valid UUID
        for forbidden in FORBIDDEN_FIELDS:
            assert forbidden not in payload_1, f"Forbidden top-level field '{forbidden}' found!"
        print(f"  -> Top-level fields: pipeline_run_id={payload_1['pipeline_run_id']}, status={payload_1['status']}, confidence={payload_1['confidence']:.4f}")
        results_summary["tests_passed"] += 1

        # Verify Matches Count and Structure
        results_summary["tests_total"] += 1
        matches = payload_1["matches"]
        assert len(matches) == 5, f"Expected 5 matches, got {len(matches)}"
        primary_match = payload_1["primary_match"]
        assert primary_match == matches[0], "primary_match does not match Rank-1 item in matches"
        assert round(primary_match["similarity_score"], 4) == round(payload_1["confidence"], 4), "confidence != primary_match.similarity_score"
        print(f"  -> Returned {len(matches)} matches. Rank 1 matches primary_match.")
        results_summary["tests_passed"] += 1

        # Field-by-field verification against catalog database
        results_summary["tests_total"] += 1
        print("\n  Verifying Rank 1..5 fields against catalog database records:")
        for idx, match in enumerate(matches, start=1):
            assert match["rank"] == idx, f"Rank mismatch at index {idx}: {match['rank']}"
            
            # Check all required fields and types
            for field_name, expected_type in REQUIRED_MATCH_FIELDS.items():
                assert field_name in match, f"Missing field '{field_name}' in match #{idx}"
                val = match[field_name]
                assert isinstance(val, expected_type), f"Field '{field_name}' has invalid type {type(val)}, expected {expected_type}"

            # Check no forbidden fields
            for forbidden in FORBIDDEN_FIELDS:
                assert forbidden not in match, f"Forbidden field '{forbidden}' in match #{idx}"

            # Verify against actual database item
            db_item = get_catalog_item(match["catalog_item_id"])
            assert db_item is not None, f"catalog_item_id {match['catalog_item_id']} not found in catalog DB!"
            
            # Verify ID distinctions
            assert match["catalog_item_id"] == db_item["id"], f"catalog_item_id {match['catalog_item_id']} != db id {db_item['id']}"
            assert match["product_id"] == db_item["product_id"], f"product_id {match['product_id']} != db product_id {db_item['product_id']}"
            assert match["filename"] == db_item["filename"], f"filename {match['filename']} != db filename {db_item['filename']}"
            assert match["image_url"] == db_item["image_url"], f"image_url {match['image_url']} != db image_url {db_item['image_url']}"
            assert match["product_display_name"] == db_item["product_display_name"], "product_display_name mismatch"
            assert match["category"] == (db_item.get("category") or db_item.get("master_category")), "category mismatch"
            assert match["sub_category"] == db_item.get("sub_category"), "sub_category mismatch"
            assert match["article_type"] == db_item.get("article_type"), "article_type mismatch"
            assert match["base_colour"] == db_item.get("base_colour"), "base_colour mismatch"
            assert match["gender"] == db_item.get("gender"), "gender mismatch"
            assert match["season"] == db_item.get("season"), "season mismatch"
            assert match["usage"] == db_item.get("usage"), "usage mismatch"

            print(f"    Rank {match['rank']}: ID={match['catalog_item_id']}, ProdID={match['product_id']}, File={match['filename']}, Sim={match['similarity_score']:.4f} | Name: '{match['product_display_name']}'")

        print("  -> All 15 fields for all matches match the catalog database records exactly!")
        results_summary["tests_passed"] += 1

        # Verify DB Persistence in Supabase
        results_summary["tests_total"] += 1
        extracted_row = get_extracted_data_by_run_id(run_id_1)
        assert extracted_row is not None, "extracted_data row missing in shared DB!"
        assert extracted_row["id"] == payload_1["extracted_data_id"], "extracted_data_id mismatch in DB"
        assert extracted_row["module"] == "vision", f"module mismatch: {extracted_row['module']}"
        assert extracted_row["data_type"] == "visual_product_search_matches", f"data_type mismatch: {extracted_row['data_type']}"
        assert round(float(extracted_row["confidence"]), 4) == round(float(payload_1["confidence"]), 4), "confidence mismatch in DB"
        
        # Verify content JSONB in DB
        content = extracted_row["content"]
        assert "primary_match" in content, "content missing primary_match in DB"
        assert "matches" in content, "content missing matches in DB"
        assert content["primary_match"]["product_id"] == primary_match["product_id"], "DB content product_id mismatch"
        print("  -> Extracted data verified in shared Supabase PostgreSQL DB")
        results_summary["tests_passed"] += 1

        # Verify Assets & Module Events
        results_summary["tests_total"] += 1
        assets = get_assets_by_run_id(run_id_1)
        assert len(assets) >= 1, "No asset recorded in shared DB"
        assert assets[0]["filename"] == "10003.jpg", f"Asset filename mismatch: {assets[0]['filename']}"
        
        events = get_module_events_by_run_id(run_id_1)
        event_types = [e["event"] for e in events]
        assert "started" in event_types, "'started' event not in module_events"
        assert "completed" in event_types, "'completed' event not in module_events"
        print(f"  -> Assets ({len(assets)}) and module events ({event_types}) verified")
        results_summary["tests_passed"] += 1

        # ====================================================================
        # PART 2: TEST POST /api/v1/gateway/run (Unified Gateway Intake Flow)
        # ====================================================================
        print("\n" + "-" * 70)
        print("PART 2: Testing POST /api/v1/gateway/run (Unified Gateway Intake Flow)")
        print("-" * 70)

        run_id_2 = str(uuid.uuid4())
        run_ids_to_clean.append(run_id_2)
        seed_orchestrator_run(run_id_2, status="processing")
        print(f"Seeded orchestrator pipeline run: {run_id_2}")

        results_summary["tests_total"] += 1
        resp_gw = client.post(
            "/api/v1/gateway/run",
            data={"run_id": run_id_2, "top_k": "5", "model": "clip"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert resp_gw.status_code == 200, f"Expected 200, got {resp_gw.status_code}: {resp_gw.text}"
        gw_payload = resp_gw.json()
        print("  -> Status: HTTP 200 OK")
        results_summary["tests_passed"] += 1

        # Validate Gateway Response
        results_summary["tests_total"] += 1
        validated_gw = GatewayRunResponse.model_validate(gw_payload)
        assert validated_gw.run_id == run_id_2
        assert validated_gw.pipeline_run_id == run_id_2
        assert validated_gw.status == "vision_complete"
        assert len(validated_gw.matches) == 5
        print(f"  -> GatewayRunResponse validated: run_id={validated_gw.run_id}, status={validated_gw.status}")
        results_summary["tests_passed"] += 1

        # Test GET /api/v1/gateway/run/{run_id}
        results_summary["tests_total"] += 1
        detail_resp = client.get(f"/api/v1/gateway/run/{run_id_2}")
        assert detail_resp.status_code == 200, f"Expected 200, got {detail_resp.status_code}: {detail_resp.text}"
        detail_payload = detail_resp.json()
        validated_detail = GatewayRunDetailResponse.model_validate(detail_payload)
        assert validated_detail.status == "vision_complete"
        assert validated_detail.vision_result is not None
        assert validated_detail.vision_result.primary_match.product_id == primary_match["product_id"]
        print(f"  -> GET /api/v1/gateway/run/{run_id_2} validated: normalized vision_result intact")
        results_summary["tests_passed"] += 1

        # ====================================================================
        # PART 3: TEST RESNET-50 ON REAL IMAGE
        # ====================================================================
        print("\n" + "-" * 70)
        print("PART 3: Testing ResNet-50 Model on Real Image")
        print("-" * 70)

        run_id_3 = str(uuid.uuid4())
        run_ids_to_clean.append(run_id_3)
        seed_orchestrator_run(run_id_3, status="processing")

        results_summary["tests_total"] += 1
        resp_resnet = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": run_id_3, "top_k": "3", "model": "resnet"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert resp_resnet.status_code == 200, f"Expected 200 for ResNet, got {resp_resnet.status_code}: {resp_resnet.text}"
        resnet_payload = resp_resnet.json()
        validated_resnet = VisionProcessResponse.model_validate(resnet_payload)
        assert len(validated_resnet.matches) == 3
        print(f"  -> ResNet-50 successful: Rank 1={validated_resnet.primary_match.product_display_name}, Score={validated_resnet.primary_match.similarity_score:.4f}")
        results_summary["tests_passed"] += 1

        # ====================================================================
        # PART 4: ERROR / VALIDATION SCENARIOS
        # ====================================================================
        print("\n" + "-" * 70)
        print("PART 4: Testing Error / Invalid Input Scenarios")
        print("-" * 70)

        # 4a. Missing pipeline_run_id
        results_summary["tests_total"] += 1
        err_missing_id = client.post(
            "/api/v1/vision/process",
            data={"top_k": "5", "model": "clip"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert err_missing_id.status_code == 422, f"Expected 422 for missing form param, got {err_missing_id.status_code}"
        print(f"  -> Missing pipeline_run_id: Returned HTTP {err_missing_id.status_code} Unprocessable Entity")
        results_summary["tests_passed"] += 1

        # 4b. Invalid UUID format
        results_summary["tests_total"] += 1
        err_invalid_uuid = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": "not-a-valid-uuid", "top_k": "5", "model": "clip"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert err_invalid_uuid.status_code == 400, f"Expected 400 for bad UUID, got {err_invalid_uuid.status_code}"
        assert "pipeline_run_id must be a valid UUID" in err_invalid_uuid.json()["detail"]
        print(f"  -> Invalid UUID format: Returned HTTP 400 with detail: '{err_invalid_uuid.json()['detail']}'")
        results_summary["tests_passed"] += 1

        # 4c. Non-existent pipeline_run_id (Unseeded run)
        results_summary["tests_total"] += 1
        non_existent_uuid = str(uuid.uuid4())
        err_not_found = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": non_existent_uuid, "top_k": "5", "model": "clip"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert err_not_found.status_code == 404, f"Expected 404 for unseeded run, got {err_not_found.status_code}"
        assert "not found in shared pipeline_runs table" in err_not_found.json()["detail"]
        print(f"  -> Non-existent pipeline_run_id: Returned HTTP 404 with detail: '{err_not_found.json()['detail']}'")
        results_summary["tests_passed"] += 1

        # 4d. Out-of-range top_k (>50)
        results_summary["tests_total"] += 1
        err_top_k = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": run_id_1, "top_k": "99", "model": "clip"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert err_top_k.status_code == 400, f"Expected 400 for top_k > 50, got {err_top_k.status_code}"
        assert "top_k must be an integer between 1 and 50" in err_top_k.json()["detail"]
        print(f"  -> Invalid top_k: Returned HTTP 400 with detail: '{err_top_k.json()['detail']}'")
        results_summary["tests_passed"] += 1

        # 4e. Unsupported model
        results_summary["tests_total"] += 1
        err_model = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": run_id_1, "top_k": "5", "model": "bert_vit"},
            files={"image": ("10003.jpg", real_image_bytes, "image/jpeg")},
        )
        assert err_model.status_code == 400, f"Expected 400 for bad model, got {err_model.status_code}"
        assert "Unsupported model" in err_model.json()["detail"]
        print(f"  -> Unsupported model: Returned HTTP 400 with detail: '{err_model.json()['detail']}'")
        results_summary["tests_passed"] += 1

        # 4f. Corrupt / empty image
        results_summary["tests_total"] += 1
        err_corrupt = client.post(
            "/api/v1/vision/process",
            data={"pipeline_run_id": run_id_1, "top_k": "5", "model": "clip"},
            files={"image": ("corrupt.jpg", b"not-an-image-data", "image/jpeg")},
        )
        assert err_corrupt.status_code == 400, f"Expected 400 for corrupt image, got {err_corrupt.status_code}"
        assert "not a valid or supported image" in err_corrupt.json()["detail"]
        print(f"  -> Corrupt image: Returned HTTP 400 with detail: '{err_corrupt.json()['detail']}'")
        results_summary["tests_passed"] += 1

        # ====================================================================
        # PART 5: DOWNSTREAM COMPATIBILITY (RAG HANDOFF CHECK)
        # ====================================================================
        print("\n" + "-" * 70)
        print("PART 5: Downstream Compatibility (RAG Module Handoff)")
        print("-" * 70)
        results_summary["tests_total"] += 1

        # Emulate Faizan's RAG module querying extracted_data by extracted_data_id
        extracted_id = payload_1["extracted_data_id"]
        with get_shared_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content, confidence, model FROM extracted_data WHERE id = %s;",
                    (extracted_id,),
                )
                row = cur.fetchone()
                assert row is not None, f"RAG query failed: row {extracted_id} not found"
                rag_content, rag_conf, rag_model = row
                
                # Verify RAG can consume primary_match directly
                rag_pm = rag_content["primary_match"]
                assert rag_pm["product_id"] == 10003
                assert rag_pm["product_display_name"] == "Nike Women As Nike Eleme White T-Shirt"
                assert len(rag_content["matches"]) == 5
                print("  -> RAG handoff successful: Faizan's query pattern 'SELECT content FROM extracted_data WHERE id = ...' works without transformation!")

        results_summary["tests_passed"] += 1

        # Summary Print
        print("\n" + "=" * 80)
        print(f"SUMMARY: ALL {results_summary['tests_passed']}/{results_summary['tests_total']} TESTS PASSED!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n[ERROR] Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print(f"\nCleaning up {len(run_ids_to_clean)} test runs from shared database...")
        cleanup_pipeline_runs(run_ids_to_clean)
        print("Cleanup completed.")


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
