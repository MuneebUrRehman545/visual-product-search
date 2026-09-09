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
from agent.orchestrator import run_agent
from agent.report import generate_report, _load_report_system_prompt
from agent.tools.echo_tool import EchoTool
from agent.tools.registry import ToolRegistry
from database import Base, get_db
from main import app

# Setup in-memory SQLite for testing
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


client = TestClient(app)


def test_report_system_prompt_loaded():
    prompt = _load_report_system_prompt()
    assert "Only use the verified findings provided below" in prompt
    assert "Limitations" in prompt
    assert "Structure the report with" in prompt


def test_fully_successful_run_produces_report_with_no_limitations():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Research Quantum Computing Milestones", status="in_progress")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step1 = models.Step(
            plan_id=plan.id,
            description="Search 2024 quantum volume records",
            intended_tool="web_search",
            status="completed",
        )
        step2 = models.Step(
            plan_id=plan.id,
            description="Search error correction breakthroughs",
            intended_tool="web_search",
            status="completed",
        )
        db.add_all([step1, step2])
        db.commit()

        tc1 = models.ToolCall(
            step_id=step1.id,
            tool_name="web_search",
            input_args={"query": "quantum volume 2024"},
            output_data={"results": [{"title": "Quantum Volume", "snippet": "Reached 2^20"}]},
            success=True,
        )
        tc2 = models.ToolCall(
            step_id=step2.id,
            tool_name="web_search",
            input_args={"query": "quantum error correction"},
            output_data={"results": [{"title": "QEC", "snippet": "Logical qubit error suppression demonstrated"}]},
            success=True,
        )
        db.add_all([tc1, tc2])
        db.commit()

        # Mock LLM generation simulating a clean report without limitations
        mock_llm = MagicMock()
        mock_llm.api_key = "test_key"
        mock_llm.generate.return_value = (
            "# Research Report: Quantum Computing Milestones\n\n"
            "## Introduction & Objective\nResearch on quantum computing breakthroughs.\n\n"
            "## Key Findings Summary\n- Quantum volume records reached 2^20.\n- Error correction demonstrated.\n\n"
            "## Quantum Volume Analysis\nDetailed findings on quantum volume.\n\n"
            "## Error Correction Breakthroughs\nDetailed findings on logical qubits."
        )

        report = generate_report(run.id, db=db, llm_client=mock_llm)

        assert report is not None
        assert report.run_id == run.id
        assert "Quantum Computing Milestones" in report.content_markdown
        assert "Limitations" not in report.content_markdown
        assert "Limitations & Gaps" not in report.content_markdown

        # Verify LLM was invoked with strict instructions noting no skipped steps
        call_args, call_kwargs = mock_llm.generate.call_args
        user_prompt = call_kwargs.get("user_message", "")
        assert "OMIT the Limitations/Gaps section entirely" in user_prompt

    finally:
        db.close()


def test_run_with_skipped_step_produces_report_with_limitations():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Analyze Data Center Energy and Efficiency", status="in_progress")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step1 = models.Step(
            plan_id=plan.id,
            description="Search data center energy usage",
            intended_tool="web_search",
            status="completed",
        )
        step2 = models.Step(
            plan_id=plan.id,
            description="Calculate PUE percentage change",
            intended_tool="calculator",
            status="skipped",
            result_ref="Skipped (hard_failure): Division by zero encountered in expression",
        )
        db.add_all([step1, step2])
        db.commit()

        tc1 = models.ToolCall(
            step_id=step1.id,
            tool_name="web_search",
            input_args={"query": "data center energy"},
            output_data={"results": [{"snippet": "Data centers consume 415 TWh electricity"}]},
            success=True,
        )
        obs2 = models.Observation(
            step_id=step2.id,
            classification="hard_failure",
            recommendation="skip_and_flag",
            reasoning="Division by zero encountered in expression",
        )
        db.add_all([tc1, obs2])
        db.commit()

        mock_llm = MagicMock()
        mock_llm.api_key = "test_key"
        mock_llm.generate.return_value = (
            "# Research Report: Analyze Data Center Energy and Efficiency\n\n"
            "## Introduction & Objective\nResearch on data center power consumption.\n\n"
            "## Key Findings Summary\n- Data centers consume 415 TWh.\n\n"
            "## Energy Consumption Findings\nDetails about electricity usage.\n\n"
            "## Limitations & Gaps\n- Calculate PUE percentage change was skipped due to division by zero."
        )

        report = generate_report(run.id, db=db, llm_client=mock_llm)

        assert report is not None
        assert "Limitations & Gaps" in report.content_markdown
        assert "Calculate PUE percentage change" in report.content_markdown
        assert "division by zero" in report.content_markdown.lower()

        # Check prompt included the skipped step info
        call_args, call_kwargs = mock_llm.generate.call_args
        user_prompt = call_kwargs.get("user_message", "")
        assert "Calculate PUE percentage change" in user_prompt
        assert "HARD_FAILURE" in user_prompt or "Division by zero" in user_prompt

    finally:
        db.close()


def test_fallback_report_omits_limitations_when_nothing_skipped():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Fallback Test Objective", status="in_progress")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step = models.Step(
            plan_id=plan.id,
            description="Inspect local config",
            intended_tool="echo",
            status="completed",
        )
        db.add(step)
        db.commit()

        tc = models.ToolCall(
            step_id=step.id,
            tool_name="echo",
            input_args={"msg": "hello"},
            output_data={"result": "hello"},
            success=True,
        )
        db.add(tc)
        db.commit()

        # Simulate LLM unavailable -> uses fallback generator
        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.generate.side_effect = Exception("LLM unavailable")
        report = generate_report(run.id, db=db, llm_client=mock_llm)

        assert report is not None
        assert "Research Report: Fallback Test Objective" in report.content_markdown
        assert "Key Findings Summary" in report.content_markdown
        assert "Limitations" not in report.content_markdown

    finally:
        db.close()


def test_fallback_report_includes_limitations_when_step_skipped():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Fallback With Skip Objective", status="in_progress")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step = models.Step(
            plan_id=plan.id,
            description="Execute failed calculation",
            intended_tool="calculator",
            status="skipped",
            result_ref="Skipped (hard_failure): Malformed expression",
        )
        db.add(step)
        db.commit()

        obs = models.Observation(
            step_id=step.id,
            classification="hard_failure",
            recommendation="skip_and_flag",
            reasoning="Malformed expression syntax",
        )
        db.add(obs)
        db.commit()

        # Simulate LLM unavailable -> fallback generator
        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.generate.side_effect = Exception("LLM unavailable")
        report = generate_report(run.id, db=db, llm_client=mock_llm)

        assert report is not None
        assert "Limitations & Gaps" in report.content_markdown
        assert "Execute failed calculation" in report.content_markdown
        assert "Malformed expression" in report.content_markdown

    finally:
        db.close()


def test_report_generation_failure_marks_run_failed():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Failing report run", status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step = models.Step(
            plan_id=plan.id,
            description="Valid step",
            intended_tool="echo",
            status="pending",
        )
        db.add(step)
        db.commit()

        registry = ToolRegistry()
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.api_key = "test_key"
        mock_llm.decide_tool_call.return_value = ("echo", {"message": "done"})
        mock_llm.generate_json.return_value = '{"classification": "success", "reasoning": "done", "is_sufficient": true}'

        with patch("agent.orchestrator.generate_report") as mock_gen_report:
            mock_gen_report.side_effect = RuntimeError("Report synthesis fatal crash")

            updated_run = run_agent(run.id, db=db, llm_client=mock_llm, registry=registry)

            assert updated_run is not None
            assert updated_run.status == "failed"
            assert updated_run.completed_at is not None
            assert updated_run.report is not None
            assert "Report synthesis fatal crash" in updated_run.report.content_markdown

    finally:
        db.close()


def test_get_run_report_endpoint():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="API Endpoint Report Test", status="in_progress")
        db.add(run)
        db.commit()
        db.refresh(run)

        # 1. 404 for non-existent run
        rand_id = uuid.uuid4()
        resp = client.get(f"/runs/{rand_id}/report")
        assert resp.status_code == 404

        # 2. 404 when run exists but has no report yet
        resp = client.get(f"/runs/{run.id}/report")
        assert resp.status_code == 404
        assert f"Report for run {run.id} not found" in resp.json()["detail"]

        # 3. 200 when report exists
        report = models.Report(
            run_id=run.id,
            content_markdown="# Final Markdown Report\n\nContent details.",
            created_at=datetime.now(timezone.utc),
        )
        db.add(report)
        db.commit()

        resp = client.get(f"/runs/{run.id}/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == str(run.id)
        assert data["content_markdown"] == "# Final Markdown Report\n\nContent details."
        assert "id" in data
        assert "created_at" in data

    finally:
        db.close()
