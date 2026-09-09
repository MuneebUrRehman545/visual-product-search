import sys
import uuid
from datetime import datetime, timedelta, timezone
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

import time
import models
from agent.evaluator import (
    CLASSIFICATION_HARD_FAILURE,
    CLASSIFICATION_INSUFFICIENT,
    CLASSIFICATION_SUCCESS,
    CLASSIFICATION_TRANSIENT_FAILURE,
    check_stopping_condition,
    classify_observation,
)
from agent.execution import execute_step
from agent.orchestrator import run_agent
from agent.self_correction import (
    ACTION_CONTINUE,
    ACTION_RETRY_REFORMULATED,
    ACTION_RETRY_SAME,
    ACTION_SKIP_AND_FLAG,
    apply_self_correction,
    decide_correction,
)
from agent.tools.base import Tool, ToolResult
from agent.tools.calculator_tool import CalculatorTool
from agent.tools.echo_tool import EchoTool
from agent.tools.registry import ToolRegistry
from agent.tools.web_search_tool import WebSearchTool
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


class TransientFailingTool(Tool):
    name = "transient_tool"
    description = "A tool that simulates transient timeouts."
    input_schema = {"type": "object", "properties": {"query": {"type": "string"}}}

    def __init__(self, fail_times: int = 1):
        self.call_count = 0
        self.fail_times = fail_times

    def execute(self, args: dict) -> ToolResult:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            return ToolResult(success=False, error_message="HTTP 429: Rate limit exceeded, timeout occurred.")
        return ToolResult(success=True, data={"result": "Recovered successfully"})


class InsufficientTool(Tool):
    name = "insufficient_tool"
    description = "A tool that returns empty or unhelpful results initially."
    input_schema = {"type": "object", "properties": {"query": {"type": "string"}}}

    def __init__(self, empty_times: int = 1):
        self.call_count = 0
        self.empty_times = empty_times

    def execute(self, args: dict) -> ToolResult:
        self.call_count += 1
        if self.call_count <= self.empty_times:
            return ToolResult(success=True, data={"results": []})
        return ToolResult(success=True, data={"results": [{"title": "Useful Info", "snippet": "Found answer."}]})


def test_classify_observation_all_categories():
    """Verify classify_observation correctly identifies all 4 categories:
    success, insufficient, transient_failure, hard_failure."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test classification", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step = models.Step(plan_id=plan.id, description="Step 1", intended_tool="tool", status="pending")
        db.add(step)
        db.commit()

        # 1. Success
        res_success = ToolResult(success=True, data={"summary": "Detailed info on AI"})
        obs_success = classify_observation(step, res_success, db=db)
        assert obs_success.classification == CLASSIFICATION_SUCCESS
        assert obs_success.recommendation == "continue"

        # 2. Insufficient
        res_insufficient = ToolResult(success=True, data={"results": []})
        obs_insufficient = classify_observation(step, res_insufficient, db=db)
        assert obs_insufficient.classification == CLASSIFICATION_INSUFFICIENT
        assert obs_insufficient.recommendation == "retry_reformulated"

        # 3. Transient failure
        res_transient = ToolResult(success=False, error_message="Connection timed out (503 Service Unavailable)")
        obs_transient = classify_observation(step, res_transient, db=db)
        assert obs_transient.classification == CLASSIFICATION_TRANSIENT_FAILURE
        assert obs_transient.recommendation == "retry_same"

        # 4. Hard failure
        res_hard = ToolResult(success=False, error_message="ZeroDivisionError: division by zero in expression 10 / 0")
        obs_hard = classify_observation(step, res_hard, db=db)
        assert obs_hard.classification == CLASSIFICATION_HARD_FAILURE
        assert obs_hard.recommendation == "skip_and_flag"
    finally:
        db.close()


def test_decide_correction_mapping_and_caps():
    """Verify decide_correction accurately maps classifications to actions and enforces retry caps."""
    # Success -> continue
    assert decide_correction(CLASSIFICATION_SUCCESS, retry_count=0) == ACTION_CONTINUE
    assert decide_correction(CLASSIFICATION_SUCCESS, retry_count=1) == ACTION_CONTINUE

    # Insufficient -> retry_reformulated on attempt 0, skip_and_flag on attempt >= 1
    assert decide_correction(CLASSIFICATION_INSUFFICIENT, retry_count=0) == ACTION_RETRY_REFORMULATED
    assert decide_correction(CLASSIFICATION_INSUFFICIENT, retry_count=1) == ACTION_SKIP_AND_FLAG
    assert decide_correction(CLASSIFICATION_INSUFFICIENT, retry_count=2) == ACTION_SKIP_AND_FLAG

    # Transient -> retry_same on attempt 0, skip_and_flag on attempt >= 1
    assert decide_correction(CLASSIFICATION_TRANSIENT_FAILURE, retry_count=0) == ACTION_RETRY_SAME
    assert decide_correction(CLASSIFICATION_TRANSIENT_FAILURE, retry_count=1) == ACTION_SKIP_AND_FLAG

    # Hard failure -> skip_and_flag immediately (0 retries)
    assert decide_correction(CLASSIFICATION_HARD_FAILURE, retry_count=0) == ACTION_SKIP_AND_FLAG
    assert decide_correction(CLASSIFICATION_HARD_FAILURE, retry_count=1) == ACTION_SKIP_AND_FLAG


def test_transient_failure_triggers_one_retry_then_moves_on():
    """Verify that a transient failure triggers exactly one retry then moves on if it fails again."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test transient failure", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step1 = models.Step(plan_id=plan.id, description="Transient step", intended_tool="transient_tool", status="pending")
        step2 = models.Step(plan_id=plan.id, description="Next step", intended_tool="echo", status="pending")
        db.add_all([step1, step2])
        db.commit()

        # Tool that fails twice with transient failure
        always_transient_tool = TransientFailingTool(fail_times=5)
        registry = ToolRegistry()
        registry.register(always_transient_tool)
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.decide_tool_call.side_effect = [
            ("transient_tool", {"query": "attempt 1"}),
            ("transient_tool", {"query": "attempt 2 (retry)"}),
            ("echo", {"message": "step 2 done"}),
        ]
        mock_llm.generate.return_value = "# Final Report\nResearch complete."
        mock_llm.generate_json.return_value = '{"is_sufficient": true, "reasoning": "Done"}'

        updated_run = run_agent(run.id, db=db, llm_client=mock_llm, registry=registry)

        db.refresh(step1)
        db.refresh(step2)

        # Step 1 should have been retried once (2 total executions) and then marked skipped
        assert always_transient_tool.call_count == 2
        assert step1.status == "skipped"
        assert "Skipped" in (step1.result_ref or "")

        # Step 2 should have completed
        assert step2.status == "completed"
        assert updated_run.status == "complete"
    finally:
        db.close()


def test_insufficient_result_triggers_one_reformulated_retry():
    """Verify that an insufficient result triggers one reformulated retry and recovers if successful."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test insufficient retry", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step = models.Step(plan_id=plan.id, description="Search data", intended_tool="insufficient_tool", status="pending")
        db.add(step)
        db.commit()

        # Tool fails first time (empty), succeeds second time (reformulated)
        insufficient_tool = InsufficientTool(empty_times=1)
        registry = ToolRegistry()
        registry.register(insufficient_tool)

        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.decide_tool_call.side_effect = [
            ("insufficient_tool", {"query": "bad query"}),
            ("insufficient_tool", {"query": "reformulated good query"}),
        ]
        mock_llm.generate.return_value = "# Final Report\nRecovered."
        mock_llm.generate_json.return_value = '{"is_sufficient": true, "reasoning": "Done"}'

        updated_run = run_agent(run.id, db=db, llm_client=mock_llm, registry=registry)

        db.refresh(step)
        assert insufficient_tool.call_count == 2
        assert step.status == "completed"
        assert updated_run.status == "complete"
    finally:
        db.close()


def test_hard_failure_skips_immediately_without_retrying():
    """Verify that a hard failure skips immediately (0 retries) and flags the step."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Test hard failure", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step1 = models.Step(plan_id=plan.id, description="Bad calc step", intended_tool="calculator", status="pending")
        step2 = models.Step(plan_id=plan.id, description="Valid step", intended_tool="echo", status="pending")
        db.add_all([step1, step2])
        db.commit()

        calc_tool = CalculatorTool()
        registry = ToolRegistry()
        registry.register(calc_tool)
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.decide_tool_call.side_effect = [
            ("calculator", {"expression": "5 / 0"}),  # Hard failure (zero division)
            ("echo", {"message": "Success on step 2"}),
        ]
        mock_llm.generate.return_value = "# Final Report\nProceeded despite skipped step."
        mock_llm.generate_json.return_value = '{"is_sufficient": true, "reasoning": "Done"}'

        updated_run = run_agent(run.id, db=db, llm_client=mock_llm, registry=registry)

        db.refresh(step1)
        db.refresh(step2)

        # Step 1 should skip immediately without retry
        assert step1.status == "skipped"
        assert "hard_failure" in (step1.result_ref or "").lower() or "skipped" in (step1.result_ref or "").lower()

        # Step 2 should complete normally
        assert step2.status == "completed"
        assert updated_run.status == "complete"
    finally:
        db.close()


def test_retry_cap_prevents_infinite_loops():
    """Verify that if all tools always fail, the retry cap stops execution and never loops infinitely."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Infinite loop prevention", status="in_progress")
        db.add(run)
        db.commit()

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()

        step1 = models.Step(plan_id=plan.id, description="Always failing step 1", intended_tool="transient_tool", status="pending")
        step2 = models.Step(plan_id=plan.id, description="Always failing step 2", intended_tool="transient_tool", status="pending")
        db.add_all([step1, step2])
        db.commit()

        always_transient_tool = TransientFailingTool(fail_times=999)
        registry = ToolRegistry()
        registry.register(always_transient_tool)

        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.decide_tool_call.return_value = ("transient_tool", {"query": "loop test"})
        mock_llm.generate.return_value = "# Report\nAll steps failed."
        mock_llm.generate_json.return_value = '{"is_sufficient": false, "reasoning": "Incomplete"}'

        updated_run = run_agent(run.id, db=db, llm_client=mock_llm, registry=registry)

        db.refresh(step1)
        db.refresh(step2)

        # Each step should have been executed exactly 2 times (1 initial + 1 retry) and then skipped
        assert always_transient_tool.call_count == 4
        assert step1.status == "skipped"
        assert step2.status == "skipped"
        assert updated_run.status == "complete"
    finally:
        db.close()


def test_stopping_condition_hard_caps():
    """Verify check_stopping_condition triggers hard safety caps for max steps and max wall-clock time."""
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Cap test", status="in_progress")
        db.add(run)
        db.commit()

        # Step count cap (15 steps)
        stopped, reason = check_stopping_condition(run.id, db=db, step_count=15)
        assert stopped is True
        assert "Hard safety cap" in reason
        assert "15" in reason

        # Wall clock time cap (600 seconds)
        stopped_time, reason_time = check_stopping_condition(run.id, db=db, step_count=2, start_time=time.time() - 650)
        assert stopped_time is True
        assert "Hard safety cap" in reason_time
        assert "10 minutes" in reason_time
    finally:
        db.close()


def test_deliberate_failure_malformed_calculator_pipeline_e2e():
    """DELIBERATE FAILURE TEST:
    A step has an intentionally malformed calculator expression (e.g. invalid syntax).
    Confirms the full end-to-end pipeline:
    1. Tool fails with syntax error
    2. Classifies as hard_failure
    3. Self-correction skips and flags the step without infinite loops or unnecessary retries
    4. Next steps continue
    5. Stopping condition evaluates gathered findings
    6. Final Markdown report is successfully generated and persisted with limitations noted.
    """
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Calculate financial ratios and verify AI stats", status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        # Step 1: Malformed calculator expression
        step1 = models.Step(
            plan_id=plan.id,
            description="Calculate ambiguous formula with bad syntax: 100 * ( / 2)",
            intended_tool="calculator",
            status="pending",
        )
        # Step 2: Valid web search / echo step
        step2 = models.Step(
            plan_id=plan.id,
            description="Summarize AI market revenue",
            intended_tool="echo",
            status="pending",
        )
        db.add_all([step1, step2])
        db.commit()

        registry = ToolRegistry()
        registry.register(CalculatorTool())
        registry.register(EchoTool())

        mock_llm = MagicMock()
        mock_llm.api_key = "fake_key"
        mock_llm.decide_tool_call.side_effect = [
            ("calculator", {"expression": "100 * ( / 2)"}),  # Syntax error
            ("echo", {"message": "AI market is projected at $1.3 trillion by 2030."}),
        ]
        mock_llm.generate.return_value = (
            "# Financial & AI Research Report\n\n"
            "## Executive Summary\n"
            "AI market is projected at $1.3 trillion.\n\n"
            "## Limitations\n"
            "- Step 1 was skipped due to malformed mathematical syntax."
        )
        mock_llm.generate_json.return_value = '{"is_sufficient": true, "reasoning": "AI stats gathered."}'

        updated_run = run_agent(run.id, db=db, llm_client=mock_llm, registry=registry)

        db.refresh(step1)
        db.refresh(step2)
        db.refresh(updated_run)

        # 1. Step 1 should be skipped due to hard failure
        assert step1.status == "skipped"
        assert step1.observation is not None
        assert step1.observation.classification == CLASSIFICATION_HARD_FAILURE
        assert step1.observation.recommendation == "skip_and_flag"
        assert "Syntax" in step1.observation.reasoning or "hard_failure" in step1.result_ref.lower() or "skipped" in step1.result_ref.lower()

        # 2. Step 2 should be completed
        assert step2.status == "completed"
        assert step2.observation is not None
        assert step2.observation.classification == CLASSIFICATION_SUCCESS

        # 3. Full run completed
        assert updated_run.status == "complete"
        assert updated_run.completed_at is not None

        # 4. Report exists with markdown content
        assert updated_run.report is not None
        assert "Financial & AI Research Report" in updated_run.report.content_markdown
        assert "Limitations" in updated_run.report.content_markdown
    finally:
        db.close()
