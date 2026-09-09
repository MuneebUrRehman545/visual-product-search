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
from agent.execution import execute_step
from agent.tools import default_registry
from agent.tools.base import Tool, ToolResult
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


def test_echo_tool_succeeds_normally():
    """Verify EchoTool succeeds when given valid input message."""
    tool = EchoTool()
    result = tool.execute({"message": "Hello Agent!"})

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data == {"echoed": "Hello Agent!"}
    assert result.error_message is None


def test_registry_catches_echo_tool_crash():
    """Verify registry catches unexpected tool exceptions (CRASH_TEST) and returns ToolResult(success=False)."""
    registry = ToolRegistry()
    registry.register(EchoTool())

    # Dispatch CRASH_TEST argument which causes EchoTool to raise RuntimeError
    result = registry.dispatch("echo", {"message": "CRASH_TEST"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.error_message is not None
    assert "CRASH_TEST" in result.error_message
    assert result.data is None


def test_dispatch_unknown_tool():
    """Verify dispatching an unregistered tool name returns a graceful failure ToolResult."""
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = registry.dispatch("unknown_tool_xyz", {"arg": "value"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.error_message is not None
    assert "Tool 'unknown_tool_xyz' is not registered." in result.error_message


def test_default_registry_has_echo_tool():
    """Verify default_registry has EchoTool registered at startup."""
    tool = default_registry.get_tool("echo")
    assert tool is not None
    assert tool.name == "echo"

    tools_list = default_registry.list_tools()
    assert len(tools_list) >= 1
    assert any(t["name"] == "echo" for t in tools_list)


def test_execute_step_success():
    """Verify execute_step calls LLM, dispatches tool, inserts ToolCall row, and returns ToolResult."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test execution", status="running")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step = models.Step(
            plan_id=plan.id,
            description="Echo a message",
            intended_tool="echo",
            status="pending",
        )
        db.add(step)
        db.commit()
        db.refresh(step)

        registry = ToolRegistry()
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.decide_tool_call.return_value = ("echo", {"message": "Hello Step!"})

        result = execute_step(step, db=db, llm_client=mock_llm, registry=registry)

        assert result.success is True
        assert result.data == {"echoed": "Hello Step!"}
        assert result.error_message is None

        # Verify DB records
        tool_call = db.query(models.ToolCall).filter(models.ToolCall.step_id == step.id).first()
        assert tool_call is not None
        assert tool_call.tool_name == "echo"
        assert tool_call.input_args == {"message": "Hello Step!"}
        assert tool_call.output_data == {"echoed": "Hello Step!"}
        assert tool_call.success is True

        db.refresh(step)
        assert step.status == "completed"
    finally:
        db.close()


def test_execute_step_unregistered_tool_handled_gracefully():
    """Verify execute_step handles LLM selecting an unregistered tool gracefully without crashing."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test invalid tool execution", status="running")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step = models.Step(
            plan_id=plan.id,
            description="Use unknown tool",
            intended_tool="unknown_tool",
            status="pending",
        )
        db.add(step)
        db.commit()
        db.refresh(step)

        registry = ToolRegistry()
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.decide_tool_call.return_value = ("nonexistent_tool", {"foo": "bar"})

        result = execute_step(step, db=db, llm_client=mock_llm, registry=registry)

        assert result.success is False
        assert "is not registered" in (result.error_message or "")

        # Verify DB tool_call row exists
        tool_call = db.query(models.ToolCall).filter(models.ToolCall.step_id == step.id).first()
        assert tool_call is not None
        assert tool_call.tool_name == "nonexistent_tool"
        assert tool_call.success is False

        db.refresh(step)
        assert step.status == "failed"
    finally:
        db.close()
