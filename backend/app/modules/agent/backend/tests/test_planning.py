import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

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
from agent.evaluator import check_stopping_condition
from agent.planning import create_plan, parse_and_validate_plan
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


def test_create_plan_normal_goal_produces_valid_multistep_plan():
    db = TestingSessionLocal()
    try:
        mock_response = json.dumps({
            "steps": [
                {"description": "Search for Tokyo rainfall data (2000-2020)", "intended_tool": "web_search"},
                {"description": "Save collected rainfall numbers to notes", "intended_tool": "file_read_write"},
                {"description": "Calculate average annual rainfall", "intended_tool": "calculator"},
                {"description": "Synthesize final conclusions", "intended_tool": "none"},
            ]
        })

        with patch("agent.planning.LLMClient.generate_json") as mock_generate_json:
            mock_generate_json.return_value = mock_response

            goal = "What was the average rainfall in Tokyo between 2000 and 2020?"
            plan = create_plan(objective_text=goal, db=db)

            assert plan is not None
            assert plan.is_current is True
            assert len(plan.steps) == 4

            step_tools = [s.intended_tool for s in plan.steps]
            assert step_tools == ["web_search", "file_read_write", "calculator", "none"]

            for step in plan.steps:
                assert step.status == "pending"
                assert step.plan_id == plan.id

            # Verify saved in DB
            db_plan = db.query(models.Plan).filter(models.Plan.id == plan.id).first()
            assert db_plan is not None
            assert len(db_plan.steps) == 4
    finally:
        db.close()


def test_create_plan_vague_goal_produces_sensible_plan():
    db = TestingSessionLocal()
    try:
        mock_response = json.dumps({
            "steps": [
                {"description": "Clarify vague research objective", "intended_tool": "none"},
                {"description": "Search web for broad background information", "intended_tool": "web_search"},
                {"description": "Summarize initial findings in workspace notes", "intended_tool": "file_read_write"},
            ]
        })

        with patch("agent.planning.LLMClient.generate_json") as mock_generate_json:
            mock_generate_json.return_value = mock_response

            vague_goal = "do research"
            plan = create_plan(objective_text=vague_goal, db=db)

            assert plan is not None
            assert len(plan.steps) >= 3
            assert plan.steps[0].description != ""
    finally:
        db.close()


def test_create_plan_malformed_llm_response_retries_once_and_fails():
    db = TestingSessionLocal()
    try:
        malformed_json_1 = "This is not valid JSON."
        malformed_json_2 = json.dumps({"steps": [{"description": "Missing intended_tool"}]})

        with patch("agent.planning.LLMClient.generate_json") as mock_generate_json:
            mock_generate_json.side_effect = [malformed_json_1, malformed_json_2]

            with pytest.raises(ValueError) as exc_info:
                create_plan(objective_text="Test goal", db=db)

            assert "Failed to generate valid plan after retry" in str(exc_info.value)
            # Verify generate_json was called exactly twice (initial call + 1 retry)
            assert mock_generate_json.call_count == 2
    finally:
        db.close()


def test_create_plan_malformed_llm_response_retry_succeeds():
    db = TestingSessionLocal()
    try:
        malformed_json = "Not JSON output"
        valid_json = json.dumps({
            "steps": [
                {"description": "Step 1 search", "intended_tool": "web_search"},
                {"description": "Step 2 calc", "intended_tool": "calculator"},
                {"description": "Step 3 report", "intended_tool": "none"},
            ]
        })

        with patch("agent.planning.LLMClient.generate_json") as mock_generate_json:
            mock_generate_json.side_effect = [malformed_json, valid_json]

            plan = create_plan(objective_text="Test goal", db=db)

            assert plan is not None
            assert len(plan.steps) == 3
            assert mock_generate_json.call_count == 2
    finally:
        db.close()


def test_check_stopping_condition_stub():
    test_id = uuid.uuid4()
    assert check_stopping_condition(test_id) == False
