import sys
from pathlib import Path
from unittest.mock import MagicMock

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
from agent.tools.base import ToolResult
from agent.tools.file_read_tool import FileReadTool
from agent.tools.file_write_tool import FileWriteTool
from agent.tools.registry import ToolRegistry
from database import Base

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


@pytest.fixture
def tmp_storage(tmp_path):
    """Provides a temporary storage directory for file tool tests."""
    return tmp_path / "storage"


def test_write_then_read_round_trip(tmp_storage):
    """Verify write-then-read round trip returns identical content."""
    run_id = "test-run-roundtrip-123"
    writer = FileWriteTool(storage_dir=tmp_storage)
    reader = FileReadTool(storage_dir=tmp_storage)

    filename = "report.txt"
    content = "This is a test research report content.\nLine 2.\nLine 3."

    write_result = writer.execute({"filename": filename, "content": content}, run_id=run_id)
    assert isinstance(write_result, ToolResult)
    assert write_result.success is True
    assert write_result.data["filename"] == filename
    assert write_result.data["bytes_written"] == len(content.encode("utf-8"))

    read_result = reader.execute({"filename": filename}, run_id=run_id)
    assert isinstance(read_result, ToolResult)
    assert read_result.success is True
    assert read_result.data["content"] == content
    assert read_result.error_message is None


def test_read_nonexistent_file_fails_gracefully(tmp_storage):
    """Verify reading a nonexistent file fails gracefully with clear error message and no crash."""
    run_id = "test-run-nonexistent-456"
    reader = FileReadTool(storage_dir=tmp_storage)

    read_result = reader.execute({"filename": "missing_file.txt"}, run_id=run_id)
    assert isinstance(read_result, ToolResult)
    assert read_result.success is False
    assert read_result.data is None
    assert read_result.error_message is not None
    assert "File not found" in read_result.error_message


def test_path_traversal_rejected_by_both_tools(tmp_storage):
    """Verify filenames containing '../' are rejected by both file_write and file_read tools."""
    run_id = "test-run-security-789"
    writer = FileWriteTool(storage_dir=tmp_storage)
    reader = FileReadTool(storage_dir=tmp_storage)

    unsafe_filenames = [
        "../outside.txt",
        "..\\outside.txt",
        "sub/../../secret.txt",
        "../dir/file.txt",
    ]

    for fname in unsafe_filenames:
        write_res = writer.execute({"filename": fname, "content": "malicious data"}, run_id=run_id)
        assert isinstance(write_res, ToolResult)
        assert write_res.success is False
        assert write_res.data is None
        assert write_res.error_message is not None
        err_lower = write_res.error_message.lower()
        assert "forbidden" in err_lower or "traversal" in err_lower or "unsafe" in err_lower

        read_res = reader.execute({"filename": fname}, run_id=run_id)
        assert isinstance(read_res, ToolResult)
        assert read_res.success is False
        assert read_res.data is None
        assert read_res.error_message is not None
        err_lower_r = read_res.error_message.lower()
        assert "forbidden" in err_lower_r or "traversal" in err_lower_r or "unsafe" in err_lower_r


def test_per_run_isolation(tmp_storage):
    """Verify two different run_ids cannot see each other's files."""
    run_id_a = "run-alpha-111"
    run_id_b = "run-beta-222"

    writer = FileWriteTool(storage_dir=tmp_storage)
    reader = FileReadTool(storage_dir=tmp_storage)

    filename = "secret_notes.txt"
    content_a = "Alpha run confidential data"

    # Write file under Run A
    write_res = writer.execute({"filename": filename, "content": content_a}, run_id=run_id_a)
    assert write_res.success is True

    # Run B tries to read the file under Run B's run_id
    read_res_b = reader.execute({"filename": filename}, run_id=run_id_b)
    assert read_res_b.success is False
    assert "File not found" in (read_res_b.error_message or "")

    # Run A reads the file successfully
    read_res_a = reader.execute({"filename": filename}, run_id=run_id_a)
    assert read_res_a.success is True
    assert read_res_a.data["content"] == content_a


def test_oversized_file_write_rejected(tmp_storage):
    """Verify file content larger than 1MB is rejected by FileWriteTool."""
    run_id = "test-run-oversized"
    writer = FileWriteTool(storage_dir=tmp_storage)

    # 1MB + 10 bytes
    huge_content = "X" * (1024 * 1024 + 10)

    write_res = writer.execute({"filename": "huge.txt", "content": huge_content}, run_id=run_id)
    assert write_res.success is False
    assert "1MB" in (write_res.error_message or "") or "exceeds" in (write_res.error_message or "")


def test_execute_step_with_file_tools(tmp_storage):
    """Verify execution engine runs file_write and file_read tools with step run_id threading."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test file operations execution", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step_write = models.Step(
            plan_id=plan.id,
            description="Write summary to summary.txt",
            intended_tool="file_read_write",
            status="pending",
        )
        db.add(step_write)
        db.commit()

        registry = ToolRegistry()
        registry.register(FileWriteTool(storage_dir=tmp_storage))
        registry.register(FileReadTool(storage_dir=tmp_storage))

        mock_llm = MagicMock()
        mock_llm.decide_tool_call.return_value = (
            "file_write",
            {"filename": "summary.txt", "content": "Summary text content."},
        )

        # Execute write step
        result_write = execute_step(step_write, db=db, llm_client=mock_llm, registry=registry)
        assert result_write.success is True
        assert result_write.data["filename"] == "summary.txt"

        # Create read step
        step_read = models.Step(
            plan_id=plan.id,
            description="Read summary from summary.txt",
            intended_tool="file_read_write",
            status="pending",
        )
        db.add(step_read)
        db.commit()

        mock_llm.decide_tool_call.return_value = ("file_read", {"filename": "summary.txt"})
        result_read = execute_step(step_read, db=db, llm_client=mock_llm, registry=registry)
        assert result_read.success is True
        assert result_read.data["content"] == "Summary text content."

    finally:
        db.close()
