import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add project root and backend paths to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

try:
    from backend.app.schemas.contracts import AgentDecision
    from backend.app.modules.agent.adapter import (
        apply_decision_rules,
        get_rag_result,
        get_vision_result,
        run_agent,
    )
    from backend.app.gateway.database import Base, SessionLocal
    from backend.app.gateway import models
except ImportError:
    try:
        from app.schemas.contracts import AgentDecision
        from app.modules.agent.adapter import (
            apply_decision_rules,
            get_rag_result,
            get_vision_result,
            run_agent,
        )
        from app.gateway.database import Base, SessionLocal
        from app.gateway import models
    except ImportError:
        from schemas.contracts import AgentDecision
        from adapter import (
            apply_decision_rules,
            get_rag_result,
            get_vision_result,
            run_agent,
        )
        from gateway.database import Base, SessionLocal
        import gateway.models as models


def test_decision_rules():
    """Unit test verifying the 4 core decision-rule mappings."""
    test_cases = [
        {
            "name": "Case 1: Complete confident vision + grounded rag -> expect generate_report",
            "vision": {
                "confidence": 0.95,
                "similarity_score": 0.95,
                "is_confident": True,
                "matched_part": "P-10023",
            },
            "rag": {
                "grounded": True,
                "complete": True,
                "citation_count": 4,
                "citations": ["doc_a.pdf", "doc_b.pdf"],
            },
            "expected": AgentDecision.generate_report,
        },
        {
            "name": "Case 2a: Complete vision + rag present but grounded=False -> expect search_more_context (generic reason)",
            "vision": {
                "confidence": 0.92,
                "similarity_score": 0.92,
                "is_confident": True,
            },
            "rag": {
                "grounded": False,
                "complete": True,
                "citations": [],
            },
            "expected": AgentDecision.search_more_context,
            "expected_reason": "Confident Vision match, but RAG context is not grounded or has thin citations.",
        },
        {
            "name": "Case 2b: Complete vision + rag grounded=True but thin citations -> expect search_more_context (accurate reason)",
            "vision": {
                "confidence": 0.92,
                "similarity_score": 0.92,
                "is_confident": True,
            },
            "rag": {
                "grounded": True,
                "complete": True,
                "thin_citations": True,
                "citations": [],
            },
            "expected": AgentDecision.search_more_context,
            "expected_reason": "RAG context is grounded but has thin citation coverage.",
        },
        {
            "name": "Case 3: Weak/low similarity vision -> expect needs_review",
            "vision": {
                "confidence": 0.45,
                "similarity_score": 0.45,
                "is_confident": False,
            },
            "rag": {
                "grounded": True,
                "complete": True,
                "citations": ["doc_a.pdf"],
            },
            "expected": AgentDecision.needs_review,
        },
        {
            "name": "Case 4: Missing rag data (None) -> expect flag_incomplete",
            "vision": {
                "confidence": 0.95,
                "similarity_score": 0.95,
                "is_confident": True,
            },
            "rag": None,
            "expected": AgentDecision.flag_incomplete,
        },
    ]

    all_passed = True
    print("=" * 70)
    print("TEST SUITE: Agent Decision Rules (backend/app/modules/agent/test_adapter.py)")
    print("=" * 70)

    for idx, tc in enumerate(test_cases, 1):
        decision, reason = apply_decision_rules(tc["vision"], tc["rag"])
        passed = decision == tc["expected"]
        if "expected_reason" in tc and reason != tc["expected_reason"]:
            passed = False
        status_label = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        print(f"[{status_label}] {tc['name']}")
        print(f"       Computed Decision : {decision.value}")
        print(f"       Expected Decision : {tc['expected'].value}")
        print(f"       Reason            : {reason}")
        print("-" * 70)

    assert all_passed, "Decision rule test cases failed"
    print("RESULT: ALL 4 DECISION RULE TESTS PASSED\n")


def test_persistence():
    """Phase 3 persistence test: verify run_agent() persists records to agent_runs and agent_actions."""
    print("=" * 70)
    print("TEST: Phase 3 DB Persistence (agent_runs & agent_actions)")
    print("=" * 70)

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSession()
    try:
        test_pipeline_run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        pipeline_run = models.PipelineRun(
            id=test_pipeline_run_id,
            status="created",
            created_at=now,
            updated_at=now,
        )
        db.add(pipeline_run)
        db.commit()

        # Execute run_agent on incomplete pipeline run
        response = asyncio.run(run_agent(test_pipeline_run_id, db=db))

        # Assert response
        assert response.pipeline_run_id == test_pipeline_run_id
        assert response.decision == AgentDecision.flag_incomplete
        assert response.status == "flagged_incomplete"

        # Assert persistence in agent_runs
        agent_run = db.query(models.AgentRun).filter(models.AgentRun.pipeline_run_id == test_pipeline_run_id).first()
        assert agent_run is not None, "agent_run row was not persisted in agent_runs table"
        assert agent_run.decision == AgentDecision.flag_incomplete.value
        assert agent_run.status == "flagged_incomplete"
        assert str(agent_run.agent_run_id) == response.agent_run_id

        # Assert persistence in agent_actions
        actions = db.query(models.AgentAction).filter(models.AgentAction.agent_run_id == response.agent_run_id).all()
        assert len(actions) >= 1, "agent_actions row was not persisted in agent_actions table"
        assert actions[0].action_type == "decision_rule_evaluation"

        # Assert pipeline_run status updated
        refreshed_run = db.query(models.PipelineRun).filter(models.PipelineRun.id == test_pipeline_run_id).first()
        assert refreshed_run.status == "agent_complete"

        print("[PASS] Successfully verified persistence in agent_runs and agent_actions tables.")
        print(f"       Persisted agent_run_id: {agent_run.agent_run_id}")
        print(f"       Persisted actions count: {len(actions)}")
        print(f"       Updated pipeline status: {refreshed_run.status}")
        print("-" * 70)
    finally:
        db.close()


def test_real_pipeline_run_integration():
    """
    Integration test calling run_agent() with REAL pipeline_run_id e28c6a52-a250-41f1-903c-ec43fb0903d3
    end-to-end against real DB (no mocks).
    Given confidence 0.9179 (above 0.70 threshold) and an ungrounded/no-answer RAG result,
    asserts decision == search_more_context.
    """
    print("=" * 70)
    print("INTEGRATION TEST: End-to-End Real Pipeline Run (e28c6a52-a250-41f1-903c-ec43fb0903d3)")
    print("=" * 70)

    real_run_id = "e28c6a52-a250-41f1-903c-ec43fb0903d3"

    # 1. Verify real vision result
    vision_result = get_vision_result(real_run_id)
    assert vision_result is not None, f"Failed to retrieve vision result for {real_run_id}"
    assert vision_result["confidence"] == 0.9179, f"Expected 0.9179, got {vision_result['confidence']}"
    assert vision_result["similarity_score"] == 0.9179
    assert vision_result["is_confident"] is True, "Expected vision to be confident (0.9179 >= 0.70)"
    print(f"[PASS] Real Vision output verified: confidence={vision_result['confidence']} (is_confident=True)")

    # 2. Verify real RAG result
    rag_result = get_rag_result(real_run_id)
    assert rag_result is not None, f"Failed to retrieve RAG result for {real_run_id}"
    assert "couldn't find" in rag_result["content"].lower(), "Expected explicit 'couldn't find' response"
    assert rag_result["grounded"] is False, "Expected grounded=False for explicit no-answer RAG content"
    print(f"[PASS] Real RAG output verified: content='{rag_result['content']}' (grounded=False)")

    # 3. Call run_agent() end-to-end
    response = asyncio.run(run_agent(real_run_id))
    print(f"[PASS] run_agent() executed successfully: agent_run_id={response.agent_run_id}")

    # 4. Assert explicit decision and status
    assert response.pipeline_run_id == real_run_id
    assert response.decision == AgentDecision.search_more_context, (
        f"Expected search_more_context, got {response.decision}"
    )
    assert response.status == "in_progress", f"Expected in_progress, got {response.status}"
    assert response.reason == "Confident Vision match, but RAG context is not grounded or has thin citations."
    assert any(a["action_type"] == "search_more_context_dispatched" for a in response.actions)
    print(f"[PASS] Decision verified: {response.decision.value}")
    print(f"[PASS] Reason verified: {response.reason}")

    # 5. Verify real DB persistence
    db = SessionLocal()
    try:
        agent_run = (
            db.query(models.AgentRun)
            .filter(models.AgentRun.pipeline_run_id == real_run_id)
            .order_by(models.AgentRun.created_at.desc())
            .first()
        )
        assert agent_run is not None, "Agent run was not persisted in real DB"
        assert str(agent_run.agent_run_id) == response.agent_run_id
        assert agent_run.decision == AgentDecision.search_more_context.value
        assert agent_run.status == "in_progress"

        pipeline_run = db.query(models.PipelineRun).filter(models.PipelineRun.id == real_run_id).first()
        assert pipeline_run.status != "agent_complete", f"pipeline_runs.status should NOT equal agent_complete"
        assert pipeline_run.status == "agent_processing", f"Expected agent_processing, got {pipeline_run.status}"

        module_event = (
            db.query(models.ModuleEvent)
            .filter(models.ModuleEvent.pipeline_run_id == real_run_id, models.ModuleEvent.module == "agent")
            .order_by(models.ModuleEvent.created_at.desc())
            .first()
        )
        assert module_event is not None, "Agent module_event was not recorded"
        assert module_event.event == "agent_processing"
        print(f"[PASS] Real DB persistence verified: pipeline_run status={pipeline_run.status}, event={module_event.event}")
    finally:
        db.close()

    print("-" * 70)
    print("RESULT: REAL PIPELINE RUN INTEGRATION TEST PASSED\n")


def test_agent_websocket_lifecycle():
    """
    WebSocket test: verify live emission of status_updated events
    for agent_processing and agent_complete upon POST /api/v1/agent/run.
    """
    print("=" * 70)
    print("TEST: WebSocket Event Streaming (agent_processing & agent_complete)")
    print("=" * 70)

    try:
        from fastapi.testclient import TestClient
        from backend.app.gateway.main import app as gateway_app
        from backend.app.gateway.events import EVENT_CATCH_UP, EVENT_STATUS_UPDATED
    except ImportError:
        from fastapi.testclient import TestClient
        from app.gateway.main import app as gateway_app
        from app.gateway.events import EVENT_CATCH_UP, EVENT_STATUS_UPDATED

    client = TestClient(gateway_app)
    real_run_id = "e28c6a52-a250-41f1-903c-ec43fb0903d3"

    with client.websocket_connect(f"/ws/pipeline/{real_run_id}") as ws:
        # 1. Initial snapshot
        snapshot = ws.receive_json()
        assert snapshot["type"] == EVENT_CATCH_UP
        print(f"[PASS] Received catch_up snapshot: status={snapshot['status']}")

        # 2. Trigger Agent Run endpoint
        post_resp = client.post("/api/v1/agent/run", json={"pipeline_run_id": real_run_id})
        assert post_resp.status_code == 200, f"Expected 200 OK, got {post_resp.status_code}"
        print(f"[PASS] POST /api/v1/agent/run returned 200 OK: decision={post_resp.json()['decision']}")

        # 3. First live event: agent_processing
        ev_processing = ws.receive_json()
        assert ev_processing["type"] == EVENT_STATUS_UPDATED
        assert ev_processing["status"] == "agent_processing"
        assert ev_processing["pipeline_run_id"] == real_run_id
        print(f"[PASS] Streamed event 1: type={ev_processing['type']}, status={ev_processing['status']}")

        # 4. Second live event: agent_processing (since search_more_context keeps status as agent_processing)
        ev_complete = ws.receive_json()
        assert ev_complete["type"] == EVENT_STATUS_UPDATED
        assert ev_complete["status"] == "agent_processing"
        assert ev_complete["pipeline_run_id"] == real_run_id
        assert ev_complete["payload"]["decision"] == "search_more_context"
        print(f"[PASS] Streamed event 2: type={ev_complete['type']}, status={ev_complete['status']}")

    print("-" * 70)
    print("RESULT: WEBSOCKET EVENT STREAMING TEST PASSED\n")


if __name__ == "__main__":
    test_decision_rules()
    test_persistence()
    test_real_pipeline_run_integration()
    test_agent_websocket_lifecycle()
    print("\nALL TEST SUITES PASSED SUCCESSFULLY.")
