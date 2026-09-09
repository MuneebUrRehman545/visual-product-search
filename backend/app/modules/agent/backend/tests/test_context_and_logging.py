import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Enable JSONB compilation on SQLite for testing
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")

import models
from agent.context import build_context_summary
from agent.execution import execute_step
from agent.tools.base import ToolResult
from agent.tools.echo_tool import EchoTool
from agent.tools.registry import ToolRegistry
from database import Base, get_db
from main import app

# In-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_multi_step_logging_rows_and_timestamps_in_order():
    """Verify that after running a multi-step plan, every step has a corresponding
    logged row with correct started_at/completed_at timestamps in chronological order,
    and tool_calls & observations are directly logged."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Multi-step research project", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step1 = models.Step(plan_id=plan.id, description="Step 1: Search data", intended_tool="echo", status="pending")
        step2 = models.Step(plan_id=plan.id, description="Step 2: Calculate stats", intended_tool="echo", status="pending")
        db.add_all([step1, step2])
        db.commit()

        registry = ToolRegistry()
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.decide_tool_call.return_value = ("echo", {"message": "Data from Step 1"})

        # Execute Step 1
        res1 = execute_step(step1, db=db, llm_client=mock_llm, registry=registry, run_id=run.id)
        assert res1.success is True

        db.refresh(step1)
        assert step1.status == "completed"
        assert step1.started_at is not None
        assert step1.completed_at is not None
        assert step1.started_at <= step1.completed_at

        # Verify DB rows created for Step 1
        tc1 = db.query(models.ToolCall).filter(models.ToolCall.step_id == step1.id).first()
        assert tc1 is not None
        assert tc1.tool_name == "echo"
        assert tc1.success is True

        obs1 = db.query(models.Observation).filter(models.Observation.step_id == step1.id).first()
        assert obs1 is not None
        assert obs1.classification in ("success", "pending_evaluation")
        assert obs1.recommendation in ("continue", "Proceed to next step")

        # Execute Step 2
        mock_llm.decide_tool_call.return_value = ("echo", {"message": "Data from Step 2"})
        res2 = execute_step(step2, db=db, llm_client=mock_llm, registry=registry, run_id=run.id)
        assert res2.success is True

        db.refresh(step2)
        assert step2.status == "completed"
        assert step2.started_at is not None
        assert step2.completed_at is not None
        assert step2.started_at >= step1.completed_at

        tc2 = db.query(models.ToolCall).filter(models.ToolCall.step_id == step2.id).first()
        assert tc2 is not None
        obs2 = db.query(models.Observation).filter(models.Observation.step_id == step2.id).first()
        assert obs2 is not None
    finally:
        db.close()


def test_build_context_summary_reflects_completed_findings_and_excludes_pending():
    """Verify build_context_summary() produces condensed summaries for completed steps only,
    and excludes pending or un-run steps."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Tokyo climate study", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step1 = models.Step(plan_id=plan.id, description="Search rainfall data", intended_tool="web_search", status="pending")
        step2 = models.Step(plan_id=plan.id, description="Calculate monthly avg", intended_tool="calculator", status="pending")
        step3 = models.Step(plan_id=plan.id, description="Save summary report", intended_tool="file_write", status="pending")
        db.add_all([step1, step2, step3])
        db.commit()

        # Before any step runs, context summary is empty
        assert build_context_summary(run.id, db=db) == ""

        # Mock step 1 completed with web search tool output
        tc1 = models.ToolCall(
            step_id=step1.id,
            tool_name="web_search",
            input_args={"query": "Tokyo rainfall"},
            output_data={"results": [{"snippet": "Tokyo receives an average of 1,528 mm of rain per year."}]},
            success=True,
        )
        step1.status = "completed"
        step1.started_at = datetime.now(timezone.utc)
        step1.completed_at = datetime.now(timezone.utc)
        db.add(tc1)
        db.commit()

        # Context summary after step 1
        summary_after_1 = build_context_summary(run.id, db=db)
        assert "Search rainfall data" in summary_after_1
        assert "Tokyo receives an average of 1,528 mm of rain per year." in summary_after_1
        assert "Calculate monthly avg" not in summary_after_1
        assert "Save summary report" not in summary_after_1

        # Mock step 2 completed with calculator output
        tc2 = models.ToolCall(
            step_id=step2.id,
            tool_name="calculator",
            input_args={"expression": "1528 / 12"},
            output_data={"result": 127.33},
            success=True,
        )
        step2.status = "completed"
        step2.started_at = datetime.now(timezone.utc)
        step2.completed_at = datetime.now(timezone.utc)
        db.add(tc2)
        db.commit()

        # Context summary after step 2
        summary_after_2 = build_context_summary(run.id, db=db)
        assert "Search rainfall data" in summary_after_2
        assert "Calculate monthly avg" in summary_after_2
        assert "127.33" in summary_after_2
        assert "Save summary report" not in summary_after_2
    finally:
        db.close()


def test_execution_engine_wires_context_summary_into_llm():
    """Verify execute_step builds context summary of prior findings and passes it to decide_tool_call."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test wiring", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step1 = models.Step(plan_id=plan.id, description="Step 1", intended_tool="echo", status="completed")
        step2 = models.Step(plan_id=plan.id, description="Step 2", intended_tool="echo", status="pending")
        db.add_all([step1, step2])
        db.commit()

        tc1 = models.ToolCall(
            step_id=step1.id,
            tool_name="echo",
            input_args={"message": "First result"},
            output_data={"echoed": "First result"},
            success=True,
        )
        db.add(tc1)
        db.commit()

        registry = ToolRegistry()
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.decide_tool_call.return_value = ("echo", {"message": "Second call"})

        execute_step(step2, db=db, llm_client=mock_llm, registry=registry, run_id=run.id)

        # Check call arguments of decide_tool_call
        mock_llm.decide_tool_call.assert_called_once()
        kwargs = mock_llm.decide_tool_call.call_args.kwargs
        assert "context_summary" in kwargs
        assert "Step 'Step 1': Echoed: First result" in kwargs["context_summary"]
    finally:
        db.close()


def test_get_run_steps_endpoint():
    """Verify GET /runs/{run_id}/steps endpoint returns full chronological log for a run."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="API steps test", status="complete")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step1 = models.Step(plan_id=plan.id, description="First step", intended_tool="echo", status="completed")
        step2 = models.Step(plan_id=plan.id, description="Second step", intended_tool="echo", status="completed")
        db.add_all([step1, step2])
        db.commit()

        tc1 = models.ToolCall(step_id=step1.id, tool_name="echo", input_args={"msg": "1"}, output_data={"res": "1"}, success=True)
        tc2 = models.ToolCall(step_id=step2.id, tool_name="echo", input_args={"msg": "2"}, output_data={"res": "2"}, success=True)
        obs1 = models.Observation(step_id=step1.id, classification="pending_evaluation", recommendation="next", reasoning="done 1")
        obs2 = models.Observation(step_id=step2.id, classification="pending_evaluation", recommendation="next", reasoning="done 2")
        db.add_all([tc1, tc2, obs1, obs2])
        db.commit()

        # Test valid run_id
        client = TestClient(app)
        response = client.get(f"/runs/{run.id}/steps")
        assert response.status_code == 200
        steps_data = response.json()
        assert len(steps_data) == 2
        assert steps_data[0]["description"] == "First step"
        assert len(steps_data[0]["tool_calls"]) == 1
        assert steps_data[0]["observation"] is not None
        assert steps_data[0]["observation"]["reasoning"] == "done 1"

        assert steps_data[1]["description"] == "Second step"
        assert len(steps_data[1]["tool_calls"]) == 1

        # Test invalid run_id
        random_id = str(uuid.uuid4())
        notFoundResp = client.get(f"/runs/{random_id}/steps")
        assert notFoundResp.status_code == 404
    finally:
        db.close()


def test_logging_direct_writes_on_step_failure():
    """Verify that if a step execution fails, failed status, timestamps, tool_calls,
    and observations are still directly written to DB."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Failing step test", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step = models.Step(plan_id=plan.id, description="Failing step", intended_tool="nonexistent", status="pending")
        db.add(step)
        db.commit()

        mock_llm = MagicMock()
        mock_llm.decide_tool_call.return_value = ("nonexistent_tool", {})

        registry = ToolRegistry()

        result = execute_step(step, db=db, llm_client=mock_llm, registry=registry, run_id=run.id)
        assert result.success is False

        db.refresh(step)
        assert step.status == "failed"
        assert step.started_at is not None
        assert step.completed_at is not None

        tc = db.query(models.ToolCall).filter(models.ToolCall.step_id == step.id).first()
        assert tc is not None
        assert tc.success is False

        obs = db.query(models.Observation).filter(models.Observation.step_id == step.id).first()
        assert obs is not None
        assert "Error" in obs.reasoning or "failed" in obs.reasoning.lower()
    finally:
        db.close()
