"""
End-to-End Retest of the Unified Pipeline after Faizan's RAG fixes.
Week 6 Day 1 Task 2 verification script.
"""

import os
import sys
import json
import time
from pathlib import Path
import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BASE_URL = "http://127.0.0.1:8000"
IMAGE_PATH = Path("data/sample_images/10003.jpg")

assert IMAGE_PATH.exists(), f"Image not found at {IMAGE_PATH}"

def run_test():
    print("=" * 70)
    print("WEEK 6 DAY 1 TASK 2: END-TO-END PIPELINE RETEST")
    print("=" * 70)
    
    # ----------------------------------------------------
    # Step 1: Create Pipeline Run
    # ----------------------------------------------------
    print("\n[Step 1] Creating new pipeline run at POST /api/v1/pipeline/run...")
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        create_resp = client.post(
            "/api/v1/pipeline/run",
            json={"user_id": "week6-day1-task2-verification"}
        )
        assert create_resp.status_code == 201, f"Failed to create run: {create_resp.text}"
        create_data = create_resp.json()
        run_id = create_data["pipeline_run_id"]
        initial_status = create_data["status"]
        print(f"  -> Pipeline Run Created: id={run_id}, status={initial_status}")

    # ----------------------------------------------------
    # Step 2: Submit Real Image to Unified Intake
    # ----------------------------------------------------
    print(f"\n[Step 2] Submitting real image ({IMAGE_PATH}) to POST /api/v1/gateway/run...")
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        with open(IMAGE_PATH, "rb") as img_file:
            files = {"image": ("10003.jpg", img_file, "image/jpeg")}
            data = {"run_id": run_id, "model": "clip", "top_k": 5}
            intake_resp = client.post("/api/v1/gateway/run", data=data, files=files)
            
        assert intake_resp.status_code == 200, f"Intake failed: {intake_resp.text}"
        intake_data = intake_resp.json()
        matches = intake_data.get('matches') or intake_data.get('content', {}).get('matches', [])
        primary_match = intake_data.get('primary_match') or intake_data.get('content', {}).get('primary_match', {})
        if not primary_match and matches:
            primary_match = matches[0]
        print(f"  -> Intake response status: {intake_resp.status_code}")
        print(f"  -> Extracted Data ID: {intake_data.get('extracted_data_id')}")
        print(f"  -> Vision Match Count: {len(matches)}")
        print(f"  -> Vision Primary Match: product_id={primary_match.get('product_id')}, "
              f"name='{primary_match.get('product_display_name')}', score={primary_match.get('similarity_score')}")

    # ----------------------------------------------------
    # Step 3: Monitor Background Poller and Pipeline Handoffs
    # ----------------------------------------------------
    print("\n[Step 3] Monitoring automated pipeline handoffs (Vision -> RAG -> Agent)...")
    max_wait_seconds = 75
    poll_interval = 2.0
    start_time = time.time()
    last_status = None
    final_record = None

    while time.time() - start_time < max_wait_seconds:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            status_resp = client.get(f"/api/v1/pipeline/run/{run_id}")
            if status_resp.status_code == 200:
                record = status_resp.json()
                current_status = record.get("status")
                if current_status != last_status:
                    print(f"  [{time.strftime('%H:%M:%S')}] Status updated: {last_status} -> {current_status}")
                    last_status = current_status
                
                # Check if agent result is recorded
                if record.get("agent_result") is not None and record.get("rag_result") is not None:
                    final_record = record
                    break
            else:
                print(f"  Warning: poll status returned {status_resp.status_code}")
                
        time.sleep(poll_interval)

    assert final_record is not None, "Pipeline did not reach Agent completion within timeout!"
    print(f"\n  -> Pipeline execution completed in {time.time() - start_time:.1f}s")
    print(f"  -> Final Status: {final_record.get('status')}")

    # ----------------------------------------------------
    # Step 4: Verify Vision Preservation
    # ----------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 4: VERIFY VISION PRESERVATION")
    print("=" * 70)
    
    vr = final_record.get("vision_result", {})
    vr_content = vr.get("content", {})
    vr_primary = vr_content.get("primary_match", {})
    
    print(f"  Extracted Data ID: {vr.get('extracted_data_id')}")
    print(f"  Module: {vr.get('module')}")
    print(f"  Data Type: {vr.get('data_type')}")
    print(f"  Model: {vr.get('model')}")
    print(f"  Confidence: {vr.get('confidence')}")
    print(f"  Primary Match Product ID: {vr_primary.get('product_id')}")
    print(f"  Primary Match Filename: {vr_primary.get('filename')}")
    print(f"  Primary Match Name: {vr_primary.get('product_display_name')}")
    print(f"  Primary Match Category: {vr_primary.get('category')}")
    print(f"  Primary Match Article Type: {vr_primary.get('article_type')}")
    print(f"  Primary Match Similarity: {vr_primary.get('similarity_score')}")

    # Verification checks
    assert vr_primary.get("product_id") == 10003, f"Wrong product ID: {vr_primary.get('product_id')}"
    assert vr_primary.get("filename") == "10003.jpg", f"Wrong filename: {vr_primary.get('filename')}"
    assert vr_primary.get("product_display_name") == "Nike Women As Nike Eleme White T-Shirt", f"Wrong name: {vr_primary.get('product_display_name')}"
    assert vr_primary.get("similarity_score") == 1.0, f"Expected 1.0 similarity, got {vr_primary.get('similarity_score')}"
    print("  [PASS] Vision information preserved perfectly!")

    # ----------------------------------------------------
    # Step 5: Verify RAG Behavior (Faizan's Fixes)
    # ----------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 5: VERIFY RAG BEHAVIOR & FAIZAN'S FIXES")
    print("=" * 70)
    
    rag = final_record.get("rag_result", {})
    rag_meta = rag.get("metadata", {})
    citations = rag_meta.get("citations", [])
    rag_content = rag.get("content", "")
    
    print(f"  RAG Document ID: {rag.get('rag_document_id')}")
    print(f"  RAG Status: {rag_meta.get('status')}")
    print(f"  RAG Content: '{rag_content}'")
    print(f"  RAG Grounded Flag: {rag_meta.get('grounded')}")
    print(f"  RAG Groundedness Score: {rag_meta.get('groundedness_score')}")
    print(f"  Citations Count: {len(citations)}")
    
    catalog_citation = next((c for c in citations if c.get("source_type") == "catalog_item"), None)
    print(f"  Catalog Item Citation: {json.dumps(catalog_citation, indent=2)}")
    
    # Assertions on RAG
    assert rag.get("rag_document_id") is not None, "Missing rag_document_id"
    assert catalog_citation is not None, "Missing catalog_item citation built by Faizan's adapter!"
    assert catalog_citation.get("product_id") == 10003, f"Citation product_id mismatch: {catalog_citation.get('product_id')}"
    assert catalog_citation.get("source") == "Nike Women As Nike Eleme White T-Shirt", f"Citation source mismatch: {catalog_citation.get('source')}"
    assert catalog_citation.get("image_url") == "/catalog-images/10003.jpg", f"Citation image_url mismatch: {catalog_citation.get('image_url')}"
    
    # Verify refusal & ungrounded behavior:
    # Because catalog product has no uploaded user documents, RAG correctly refuses rather than hallucinating
    assert "couldn't find" in rag_content.lower(), f"Expected honest refusal in content, got: {rag_content}"
    print("  [PASS] RAG received Vision data and built catalog citation accurately!")
    print("  [PASS] RAG refusal behavior verified (honest response without hallucination)!")

    # ----------------------------------------------------
    # Step 6: Verify Final Agent Input & Output
    # ----------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 6: VERIFY FINAL AGENT INPUT & TRIAGE OUTPUT")
    print("=" * 70)
    
    agent = final_record.get("agent_result", {})
    print(f"  Agent Run ID: {agent.get('agent_run_id')}")
    print(f"  Agent Status: {agent.get('status')}")
    print(f"  Agent Decision: {agent.get('decision')}")
    print(f"  Agent Reason: {agent.get('reason')}")
    
    assert agent.get("agent_run_id") is not None, "Missing agent_run_id"
    assert agent.get("decision") == "search_more_context", f"Expected search_more_context, got: {agent.get('decision')}"
    assert "Confident Vision match" in agent.get("reason"), f"Unexpected reason: {agent.get('reason')}"
    assert agent.get("status") == "in_progress", f"Expected status 'in_progress', got: {agent.get('status')}"
    print("  [PASS] Agent received real Vision + RAG context and applied intelligent triage!")

    # ----------------------------------------------------
    # Step 7: Verify Complete Audit Events
    # ----------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 7: AUDIT EVENTS LOGGED")
    print("=" * 70)
    events = final_record.get("events", [])
    print(f"  Total lifecycle events recorded: {len(events)}")
    for ev in events:
        print(f"    [{ev.get('module')}] event={ev.get('event')}: {ev.get('message')}")

    # Check required events exist
    event_names = [e.get("event") for e in events]
    assert "created" in event_names
    assert "started" in event_names
    assert "completed" in event_names
    assert "rag_processing" in event_names
    assert "rag_started" in event_names
    assert "rag_completed" in event_names
    assert "agent_processing" in event_names
    print("  [PASS] Full event trail recorded cleanly in PostgreSQL!")

    # ----------------------------------------------------
    # Step 8: Controlled Failure / Invalid-Input Case
    # ----------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 8: CONTROLLED PARTIAL-FAILURE TEST")
    print("=" * 70)
    
    # Create an unseeded run, manually set status to vision_complete without extracted_data
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        fail_create_resp = client.post(
            "/api/v1/pipeline/run",
            json={"user_id": "auto-failure-test"}
        )
        fail_run_id = fail_create_resp.json()["pipeline_run_id"]
        print(f"  Created unseeded run: {fail_run_id}")

    # Inject vision_complete directly into DB
    from app.db.shared_database import get_shared_connection
    with get_shared_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE pipeline_runs SET status = 'vision_complete', updated_at = NOW() WHERE id = %s;",
                (fail_run_id,)
            )

    print("  Injected 'vision_complete' state without extracted_data row.")
    print("  Waiting for poller to catch error and transition to 'rag_failed'...")

    fail_final = None
    start_fail = time.time()
    while time.time() - start_fail < 35:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            st = client.get(f"/api/v1/pipeline/run/{fail_run_id}").json()
            if st.get("status") == "rag_failed":
                fail_final = st
                break
        time.sleep(1.0)

    assert fail_final is not None, "Failed run did not transition to rag_failed!"
    print(f"  -> Run cleanly transitioned to '{fail_final.get('status')}' in {time.time() - start_fail:.1f}s")
    
    # Check failure events
    fail_events = fail_final.get("events", [])
    fail_ev = next((e for e in fail_events if e.get("event") == "rag_failed"), None)
    assert fail_ev is not None, "Missing rag_failed audit event"
    print(f"  -> Captured Failure Message: '{fail_ev.get('message')}'")
    print("  [PASS] Controlled partial-failure verified: graceful status update, audit logged, server process healthy!")

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)
    return run_id, fail_run_id, final_record, fail_final

if __name__ == "__main__":
    run_test()
