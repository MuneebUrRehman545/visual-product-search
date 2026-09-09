import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Union

from sqlalchemy.orm import Session

import models
from agent.context import build_context_summary
from agent.llm_client import LLMClient, LLMClientError
from agent.tools.base import ToolResult
from database import get_db

logger = logging.getLogger(__name__)

# Allowed observation classifications
CLASSIFICATION_SUCCESS = "success"
CLASSIFICATION_INSUFFICIENT = "insufficient"
CLASSIFICATION_TRANSIENT_FAILURE = "transient_failure"
CLASSIFICATION_HARD_FAILURE = "hard_failure"

DEFAULT_RECOMMENDATIONS = {
    CLASSIFICATION_SUCCESS: "continue",
    CLASSIFICATION_INSUFFICIENT: "retry_reformulated",
    CLASSIFICATION_TRANSIENT_FAILURE: "retry_same",
    CLASSIFICATION_HARD_FAILURE: "skip_and_flag",
}


class ObservationResult:
    """Represents the structured evaluation of a tool execution outcome."""

    def __init__(
        self,
        classification: str,
        reasoning: str,
        recommendation: Optional[str] = None,
    ):
        self.classification = classification
        self.reasoning = reasoning
        self.recommendation = recommendation or DEFAULT_RECOMMENDATIONS.get(classification, "continue")

    def __iter__(self):
        return iter((self.classification, self.reasoning))

    def __getitem__(self, index):
        return (self.classification, self.reasoning)[index]

    def __repr__(self):
        return (
            f"ObservationResult(classification='{self.classification}', "
            f"reasoning='{self.reasoning}', recommendation='{self.recommendation}')"
        )


class StoppingConditionResult(tuple):
    """Represents the result of check_stopping_condition as a 2-tuple (should_stop, reasoning)
    with property access and boolean evaluation support."""

    def __new__(cls, should_stop: bool, reasoning: str):
        return super().__new__(cls, (should_stop, reasoning))

    @property
    def should_stop(self) -> bool:
        return self[0]

    @property
    def reasoning(self) -> str:
        return self[1]

    def __bool__(self) -> bool:
        return bool(self[0])

    def __eq__(self, other):
        if isinstance(other, bool):
            return self[0] == other
        return super().__eq__(other)


def _heuristic_classify(tool_result: ToolResult) -> Tuple[str, str]:
    """Deterministic fallback classification when LLM is unavailable or unparseable."""
    if not tool_result.success:
        err = (tool_result.error_message or "").lower()
        transient_indicators = [
            "timeout",
            "timed out",
            "rate limit",
            "429",
            "503",
            "connection reset",
            "connection error",
            "temporarily unavailable",
            "try again",
        ]
        if any(ind in err for ind in transient_indicators):
            return (
                CLASSIFICATION_TRANSIENT_FAILURE,
                f"Transient failure (Error: {tool_result.error_message or 'Temporary error occurred'}).",
            )
        return (
            CLASSIFICATION_HARD_FAILURE,
            f"Hard failure (Error: {tool_result.error_message or 'Tool execution failed'}).",
        )

    # Success=True check
    data = tool_result.data
    if data is None:
        return CLASSIFICATION_INSUFFICIENT, "Tool completed with success=True but returned no output data."

    if isinstance(data, dict):
        if "results" in data and isinstance(data["results"], list) and len(data["results"]) == 0:
            return CLASSIFICATION_INSUFFICIENT, "Search completed with success=True but returned 0 results."
        if not data:
            return CLASSIFICATION_INSUFFICIENT, "Tool returned an empty data object."

    if isinstance(data, (list, str)) and len(data) == 0:
        return CLASSIFICATION_INSUFFICIENT, "Tool returned empty content."

    return CLASSIFICATION_SUCCESS, "Tool executed successfully with informative results."


def classify_observation(
    step: Union[models.Step, str, uuid.UUID],
    tool_result: Union[ToolResult, dict, Any],
    llm_client: Optional[LLMClient] = None,
    db: Optional[Session] = None,
    objective_text: Optional[str] = None,
) -> ObservationResult:
    """Evaluates the outcome of a step's tool execution using the LLM and returns an ObservationResult.
    Saves or updates the classification and reasoning in the observations table.

    Classifications:
    - "success": the tool worked and gave genuinely useful information
    - "insufficient": the tool ran without error, but the result doesn't actually help answer the goal
    - "transient_failure": the tool call failed in a way likely to succeed if retried (timeout, rate limit)
    - "hard_failure": the tool failed in a way retrying won't fix (malformed input, auth error, invalid expression)
    """
    if not isinstance(tool_result, ToolResult):
        if isinstance(tool_result, dict):
            tool_result = ToolResult(
                success=tool_result.get("success", True),
                data=tool_result.get("data") or tool_result.get("output_data"),
                error_message=tool_result.get("error_message"),
            )
        else:
            tool_result = ToolResult(success=True, data=tool_result)

    own_db = False
    db_gen = None
    if db is None:
        try:
            from main import app
            db_provider = app.dependency_overrides.get(get_db, get_db)
        except Exception:
            db_provider = get_db

        db_gen = db_provider()
        db = next(db_gen)
        own_db = True

    try:
        step_obj: Optional[models.Step] = None
        if isinstance(step, (str, uuid.UUID)):
            step_id_val = uuid.UUID(str(step))
            step_obj = db.query(models.Step).filter(models.Step.id == step_id_val).first()
        elif isinstance(step, models.Step):
            step_obj = step
            if db:
                step_obj = db.merge(step_obj)

        step_desc = step_obj.description if step_obj else str(step)
        intended_tool = step_obj.intended_tool if step_obj else "unknown"

        goal = objective_text
        if not goal and step_obj and step_obj.plan and step_obj.plan.run:
            goal = step_obj.plan.run.goal_text

        classification: Optional[str] = None
        reasoning: Optional[str] = None

        # Attempt LLM classification if llm_client has a real string api_key
        api_key = getattr(llm_client, "api_key", None)
        if isinstance(api_key, str) and api_key.strip():
            try:
                system_prompt = (
                    "You are an expert AI research agent evaluator. Your job is to classify tool execution outcomes "
                    "strictly and accurately into one of 4 defined categories."
                )

                data_preview = str(tool_result.data) if tool_result.data is not None else "None"
                if len(data_preview) > 500:
                    data_preview = data_preview[:497] + "..."

                user_prompt = f"""Evaluate this step execution:
Step Description: {step_desc}
Intended Tool: {intended_tool}
Research Goal: {goal or 'Unspecified'}

Outcome:
- Success: {tool_result.success}
- Error Message: {tool_result.error_message or 'None'}
- Data: {data_preview}

Classify into EXACTLY ONE of:
1. "success": Tool succeeded and produced relevant, useful information for the step.
2. "insufficient": Tool ran without error, but returned empty, irrelevant, or non-informative results.
3. "transient_failure": Tool failed due to temporary issue likely to resolve on immediate retry (timeout, 429 rate limit, 503, connection reset).
4. "hard_failure": Tool failed due to an unrecoverable error (malformed math expression, invalid syntax, auth error, division by zero, invalid tool args).

Output JSON:
{{
  "classification": "success" | "insufficient" | "transient_failure" | "hard_failure",
  "reasoning": "1-2 sentence explanation of the evaluation"
}}"""

                raw_json = llm_client.generate_json(system_prompt=system_prompt, user_message=user_prompt)
                parsed = json.loads(raw_json)
                cand_class = str(parsed.get("classification", "")).strip().lower()
                cand_reasoning = str(parsed.get("reasoning", "")).strip()

                if cand_class in {
                    CLASSIFICATION_SUCCESS,
                    CLASSIFICATION_INSUFFICIENT,
                    CLASSIFICATION_TRANSIENT_FAILURE,
                    CLASSIFICATION_HARD_FAILURE,
                }:
                    classification = cand_class
                    reasoning = cand_reasoning or f"Classified as {cand_class} by LLM."
            except Exception as llm_err:
                logger.warning(f"LLM observation classification failed: {llm_err}. Using heuristic fallback.")

        # Fallback if LLM classification was not performed or failed
        if not classification or not reasoning:
            classification, reasoning = _heuristic_classify(tool_result)

        recommendation = DEFAULT_RECOMMENDATIONS.get(classification, "continue")
        obs_result = ObservationResult(
            classification=classification,
            reasoning=reasoning,
            recommendation=recommendation,
        )

        # Persist observation in DB if step_obj is available
        if step_obj and db:
            existing_obs = db.query(models.Observation).filter(models.Observation.step_id == step_obj.id).first()
            if existing_obs:
                existing_obs.classification = classification
                existing_obs.reasoning = reasoning
                existing_obs.recommendation = recommendation
            else:
                new_obs = models.Observation(
                    step_id=step_obj.id,
                    classification=classification,
                    reasoning=reasoning,
                    recommendation=recommendation,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(new_obs)
            try:
                db.commit()
            except Exception as db_err:
                logger.error(f"Failed to persist observation for step {step_obj.id}: {db_err}")
                db.rollback()

        return obs_result

    finally:
        if own_db and db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass


def check_stopping_condition(
    run_id: Union[str, uuid.UUID],
    db: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    step_count: int = 0,
    start_time: Optional[Union[datetime, float]] = None,
) -> StoppingConditionResult:
    """Evaluates whether the agent run should stop.

    1. Checks HARD SAFETY CAP: max 15 steps OR max 10 minutes (600s) wall-clock time.
       If hit, stops immediately and notes the cap reason.
    2. If within safety caps, queries the original objective and build_context_summary(run_id),
       and asks the LLM: 'given what's been found so far, is this enough to write a good report,
       or is more research needed?'

    Returns StoppingConditionResult(should_stop: bool, reasoning: str).
    """
    # 1. HARD SAFETY CAP CHECKS
    MAX_STEPS = 15
    MAX_WALL_CLOCK_SECONDS = 600  # 10 minutes

    if step_count >= MAX_STEPS:
        msg = f"Hard safety cap reached: maximum step limit ({MAX_STEPS}) reached."
        logger.warning(msg)
        return StoppingConditionResult(True, msg)

    now_ts = time.time()
    elapsed_seconds = 0.0
    if isinstance(start_time, (int, float)):
        elapsed_seconds = now_ts - float(start_time)
    elif isinstance(start_time, datetime):
        now_dt = datetime.now(timezone.utc)
        if start_time.tzinfo is None:
            start_dt = start_time.replace(tzinfo=timezone.utc)
        else:
            start_dt = start_time
        elapsed_seconds = (now_dt - start_dt).total_seconds()

    if elapsed_seconds >= MAX_WALL_CLOCK_SECONDS:
        msg = f"Hard safety cap reached: maximum wall-clock duration of 10 minutes exceeded ({int(elapsed_seconds)}s elapsed)."
        logger.warning(msg)
        return StoppingConditionResult(True, msg)

    own_db = False
    db_gen = None
    if db is None:
        try:
            from main import app
            db_provider = app.dependency_overrides.get(get_db, get_db)
        except Exception:
            db_provider = get_db

        try:
            db_gen = db_provider()
            db = next(db_gen)
            own_db = True
        except Exception:
            return StoppingConditionResult(False, "Database session not available.")

    try:
        run_uuid = uuid.UUID(str(run_id)) if isinstance(run_id, str) else run_id
        try:
            run = db.query(models.Run).filter(models.Run.id == run_uuid).first()
        except Exception:
            run = None

        if not run:
            return StoppingConditionResult(False, f"Run {run_id} not found.")

        # Check elapsed time against run.created_at if start_time wasn't provided
        if start_time is None and run.created_at:
            now_dt = datetime.now(timezone.utc)
            run_created = run.created_at if run.created_at.tzinfo else run.created_at.replace(tzinfo=timezone.utc)
            if (now_dt - run_created).total_seconds() >= MAX_WALL_CLOCK_SECONDS:
                msg = "Hard safety cap reached: maximum wall-clock duration of 10 minutes exceeded."
                return StoppingConditionResult(True, msg)

        # Count pending steps in current plan
        try:
            pending_steps = (
                db.query(models.Step)
                .join(models.Plan, models.Step.plan_id == models.Plan.id)
                .filter(
                    models.Plan.run_id == run_uuid,
                    models.Plan.is_current == True,
                    models.Step.status == "pending",
                )
                .count()
            )
        except Exception:
            pending_steps = 0

        try:
            context_summary = build_context_summary(run_uuid, db=db)
        except Exception:
            context_summary = ""

        # If no steps have finished and pending steps remain, keep going
        if not context_summary.strip() and pending_steps > 0:
            return StoppingConditionResult(False, "Initial steps in progress; insufficient data to evaluate stopping.")

        # 2. LLM EVALUATION
        api_key = getattr(llm_client, "api_key", None)
        if isinstance(api_key, str) and api_key.strip():
            try:
                system_prompt = (
                    "You are an AI research evaluator deciding whether enough research has been gathered "
                    "to write a comprehensive and high-quality report."
                )
                user_prompt = f"""Original Research Objective: {run.goal_text}

Findings gathered so far:
{context_summary.strip() if context_summary.strip() else 'None yet.'}

Given what has been found so far, is this enough information to write a good, well-rounded research report, or is more research needed?

Output JSON:
{{
  "is_sufficient": true | false,
  "reasoning": "1-2 sentence explanation of your decision"
}}"""

                raw_json = llm_client.generate_json(system_prompt=system_prompt, user_message=user_prompt)
                parsed = json.loads(raw_json)
                is_sufficient = bool(parsed.get("is_sufficient", False))
                eval_reasoning = str(parsed.get("reasoning", "")).strip()

                if is_sufficient:
                    return StoppingConditionResult(True, eval_reasoning or "Evaluator determined enough information has been gathered to write the report.")

                if pending_steps == 0:
                    return StoppingConditionResult(True, f"All plan steps completed. (Evaluator note: {eval_reasoning or 'Research finalized'})")

                return StoppingConditionResult(False, eval_reasoning or "More research needed to satisfy the objective.")

            except Exception as llm_err:
                logger.warning(f"LLM stopping condition check failed: {llm_err}. Falling back to step count check.")

        # Fallback heuristic
        if pending_steps == 0:
            return StoppingConditionResult(True, "All planned research steps have finished execution.")

        return StoppingConditionResult(False, f"{pending_steps} planned steps remain to be executed.")

    finally:
        if own_db and db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass
