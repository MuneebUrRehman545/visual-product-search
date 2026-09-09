import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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
from agent.llm_client import LLMClientError
from agent.orchestrator import run_agent
from agent.tools.base import ToolResult
from agent.tools.echo_tool import EchoTool
from agent.tools.registry import ToolRegistry
from database import Base

# Setup in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_run_agent_success():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Research AI trends", status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step = models.Step(
            plan_id=plan.id,
            description="Test step",
            intended_tool="echo",
            status="pending",
        )
        db.add(step)
        db.commit()

        registry = ToolRegistry()
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.decide_tool_call.return_value = ("echo", {"message": "AI trends found"})
        mock_llm.generate.return_value = "# AI Trends Report\n\nAI is growing rapidly."
        mock_llm.generate_json.return_value = '{"classification": "success", "reasoning": "Got good data", "is_sufficient": true}'

        updated_run = run_agent(run.id, db=db, llm_client=mock_llm, registry=registry)

        assert updated_run is not None
        assert updated_run.status == "complete"
        assert updated_run.completed_at is not None
        assert updated_run.report is not None
        assert "AI Trends Report" in updated_run.report.content_markdown
    finally:
        db.close()


def test_run_agent_failure_marks_failed():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Failing goal", status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        with patch("agent.orchestrator.create_plan") as mock_create_plan:
            mock_create_plan.side_effect = Exception("Planning failed error")

            updated_run = run_agent(run.id, db=db)

            assert updated_run is not None
            assert updated_run.status == "failed"
            assert updated_run.completed_at is not None
            assert updated_run.report is not None
            assert "Planning failed error" in updated_run.report.content_markdown
    finally:
        db.close()
