import asyncio
import sys
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Setup python path to include backend root
BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.gateway.database import Base, get_db
from backend.app.gateway.events import (
    EVENT_CATCH_UP,
    EVENT_STATUS_UPDATED,
    pipeline_event_emitter,
)
from backend.app.gateway.main import app
from backend.app.gateway import service
from backend.app.schemas.contracts import PipelineStatus

# Configure isolated in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Create all tables in test database
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_exit_gate_pipeline_lifecycle():
    """
    Verification test proving Week 5 Day 1 Step 2 Exit Gate:
    1. Create a run -> receive a valid run_id & initial status 'created'
    2. GET status -> returns valid initial state (not 404, not empty, null unreached stages)
    3. Connect to WebSocket channel -> receive initial snapshot -> simulate status update -> confirm it streams back
    4. Verify 404 behavior for unknown run IDs
    5. Verify route stubs return HTTP 501 Not Implemented
    """
    print("=" * 80)
    print("STARTING EXIT GATE VERIFICATION TEST: Gateway Lifecycle & Event Channel")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. Create a new pipeline run (POST /api/v1/pipeline/run)
    # -------------------------------------------------------------------------
    print("\n[Step 1] POST /api/v1/pipeline/run - Creating a new pipeline run...")
    response = client.post(
        "/api/v1/pipeline/run",
        json={"user_id": "test-user-01", "metadata": {"source": "exit_gate_verification"}},
    )
    assert response.status_code == 201, f"Expected 201 Created, got {response.status_code}: {response.text}"
    data = response.json()
    run_id = data.get("pipeline_run_id")
    initial_status = data.get("status")

    assert run_id is not None, "pipeline_run_id must not be None"
    # Validate valid UUID
    parsed_uuid = uuid.UUID(run_id)
    assert str(parsed_uuid) == run_id, f"Invalid UUID format: {run_id}"
    assert initial_status == PipelineStatus.CREATED.value, f"Expected status 'created', got '{initial_status}'"
    print(f"  [PASS] Created pipeline_run_id: {run_id}")
    print(f"  [PASS] Initial status: {initial_status}")

    # -------------------------------------------------------------------------
    # 2. GET pipeline run status (GET /api/v1/pipeline/run/{run_id})
    # -------------------------------------------------------------------------
    print(f"\n[Step 2] GET /api/v1/pipeline/run/{run_id} - Checking initial state...")
    get_res = client.get(f"/api/v1/pipeline/run/{run_id}")
    assert get_res.status_code == 200, f"Expected 200 OK, got {get_res.status_code}: {get_res.text}"
    status_data = get_res.json()

    assert status_data["pipeline_run_id"] == run_id
    assert status_data["status"] == PipelineStatus.CREATED.value
    assert status_data["vision_result"] is None, "Vision result should be None for unreached stage"
    assert status_data["rag_result"] is None, "RAG result should be None for unreached stage"
    assert status_data["agent_result"] is None, "Agent result should be None for unreached stage"
    assert len(status_data["events"]) >= 1, "Should have at least 1 creation event"
    assert status_data["events"][0]["module"] == "gateway"
    assert status_data["events"][0]["event"] == "created"
    print(f"  [PASS] Status response valid. Stage results correctly null/empty.")
    print(f"  [PASS] Event audit log recorded: {status_data['events'][0]}")

    # -------------------------------------------------------------------------
    # 3. Connect to WebSocket channel & stream status update
    # -------------------------------------------------------------------------
    print(f"\n[Step 3] WebSocket /ws/pipeline/{run_id} - Testing event streaming...")
    with client.websocket_connect(f"/ws/pipeline/{run_id}") as websocket:
        # A. Verify initial catch-up snapshot on connect
        snapshot = websocket.receive_json()
        assert snapshot["type"] == EVENT_CATCH_UP, f"Expected catch_up event, got {snapshot}"
        assert snapshot["pipeline_run_id"] == run_id
        assert snapshot["status"] == PipelineStatus.CREATED.value
        print(f"  [PASS] Received WebSocket snapshot on connect: type={snapshot['type']}, status={snapshot['status']}")

        # B. Simulate a status transition to 'vision_processing' via service layer
        db = TestingSessionLocal()
        try:
            updated_run = service.update_pipeline_status(
                db=db,
                pipeline_run_id=run_id,
                new_status=PipelineStatus.VISION_PROCESSING,
                module="vision",
                message="Vision module started processing query image.",
                payload={"image_id": "img-001.jpg"},
            )
            assert updated_run is not None
        finally:
            db.close()

        # C. Confirm the live event was received over the open WebSocket
        streamed_event = websocket.receive_json()
        assert streamed_event["type"] == EVENT_STATUS_UPDATED
        assert streamed_event["status"] == PipelineStatus.VISION_PROCESSING.value
        assert streamed_event["pipeline_run_id"] == run_id
        assert streamed_event["message"] == "Vision module started processing query image."
        assert streamed_event["payload"]["image_id"] == "img-001.jpg"
        print(f"  [PASS] Successfully streamed live event: {streamed_event}")

    # -------------------------------------------------------------------------
    # 4. Verify 404 handling on non-existent run_id
    # -------------------------------------------------------------------------
    print("\n[Step 4] Verifying 404 error handling for non-existent pipeline run...")
    fake_id = str(uuid.uuid4())
    not_found_res = client.get(f"/api/v1/pipeline/run/{fake_id}")
    assert not_found_res.status_code == 404, f"Expected 404, got {not_found_res.status_code}"
    print(f"  [PASS] Non-existent ID returned 404: {not_found_res.json()}")

    # -------------------------------------------------------------------------
    # 5. Verify Route Stubs (501 Not Implemented)
    # -------------------------------------------------------------------------
    print("\n[Step 5] Verifying route stubs return HTTP 501 Not Implemented...")
    vision_stub = client.post("/api/v1/vision/run")
    assert vision_stub.status_code == 501, f"Expected 501, got {vision_stub.status_code}"
    assert vision_stub.json()["owner"] == "Muneeb"

    rag_stub = client.post("/api/v1/rag/run")
    assert rag_stub.status_code == 501, f"Expected 501, got {rag_stub.status_code}"
    assert rag_stub.json()["owner"] == "Faizan"

    agent_stub = client.post("/api/v1/agent/decision")
    assert agent_stub.status_code == 501, f"Expected 501, got {agent_stub.status_code}"
    assert agent_stub.json()["owner"] == "Moeez"
    # -------------------------------------------------------------------------
    # TODO: add a failure-path test (e.g. status -> vision_failed) once Vision/
    # RAG failure contracts are implemented in Steps 3-4.
    # -------------------------------------------------------------------------

    print("\n" + "=" * 80)
    print("EXIT GATE VERIFICATION COMPLETE: ALL 5 CHECKS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    test_exit_gate_pipeline_lifecycle()


