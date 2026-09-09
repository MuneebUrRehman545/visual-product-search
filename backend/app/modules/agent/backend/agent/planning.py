import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

import models
from agent.events import EVENT_PLAN_CREATED, event_emitter
from agent.llm_client import LLMClient, LLMClientError
from database import get_db

logger = logging.getLogger(__name__)

ALLOWED_TOOLS = {"web_search", "file_read_write", "calculator", "none"}


class StepPlan(BaseModel):
    description: str
    intended_tool: str

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Step description cannot be empty")
        return v.strip()

    @field_validator("intended_tool")
    @classmethod
    def validate_intended_tool(cls, v: str) -> str:
        val = v.strip().lower() if v else ""
        if val not in ALLOWED_TOOLS:
            raise ValueError(f"intended_tool must be one of {ALLOWED_TOOLS}, got '{v}'")
        return val


class PlanSchema(BaseModel):
    steps: List[StepPlan]

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v: List[StepPlan]) -> List[StepPlan]:
        if not v or len(v) == 0:
            raise ValueError("Plan must contain at least one step")
        return v


def parse_and_validate_plan(json_str: str) -> List[StepPlan]:
    """Parses JSON string and validates it against the step plan schema."""
    data = json.loads(json_str)

    if isinstance(data, list):
        steps = [StepPlan.model_validate(item) for item in data]
    elif isinstance(data, dict):
        if "steps" in data and isinstance(data["steps"], list):
            plan_obj = PlanSchema.model_validate(data)
            steps = plan_obj.steps
        elif "plan" in data and isinstance(data["plan"], list):
            steps = [StepPlan.model_validate(item) for item in data["plan"]]
        else:
            raise ValueError("JSON object does not contain a 'steps' list")
    else:
        raise ValueError("JSON response must be a list or an object containing 'steps'")

    if not steps:
        raise ValueError("Plan steps list cannot be empty")

    return steps


def _load_planning_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / "planning_prompt.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def create_plan(
    objective_text: str,
    run_id: Optional[Union[str, uuid.UUID]] = None,
    db: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
) -> models.Plan:
    """Creates a structured multi-step plan for a research objective.

    1. Calls the LLM with the planning prompt to get a JSON step breakdown.
    2. Validates the JSON response. If malformed, retries once with stricter instructions.
    3. Saves the plan and step rows to DB with status='pending'.
    """
    if not objective_text or not objective_text.strip():
        raise ValueError("objective_text cannot be empty")

    if llm_client is None:
        llm_client = LLMClient()

    system_prompt = _load_planning_prompt()

    # Attempt 1: Call LLM
    validated_steps: Optional[List[StepPlan]] = None
    try:
        raw_json = llm_client.generate_json(
            system_prompt=system_prompt,
            user_message=objective_text,
            response_schema=PlanSchema,
        )
        validated_steps = parse_and_validate_plan(raw_json)
    except Exception as first_err:
        logger.warning(
            f"Planning LLM attempt 1 response was malformed: {first_err}. "
            "Retrying once with stricter instructions..."
        )

    # Attempt 2 (Retry once if attempt 1 failed validation)
    if validated_steps is None:
        stricter_user_message = (
            f"Research Objective: {objective_text}\n\n"
            "IMPORTANT: Your previous output was invalid or malformed.\n"
            "You MUST return a valid JSON object matching this structure:\n"
            '{\n  "steps": [\n    {"description": "...", "intended_tool": "web_search"|"file_read_write"|"calculator"|"none"}\n  ]\n}\n'
            "Ensure step descriptions are non-empty and intended_tool is strictly one of the 4 allowed values. Provide 3 to 7 steps."
        )
        try:
            raw_json = llm_client.generate_json(
                system_prompt=system_prompt,
                user_message=stricter_user_message,
                response_schema=PlanSchema,
            )
            validated_steps = parse_and_validate_plan(raw_json)
        except Exception as retry_err:
            logger.error(f"Planning LLM retry attempt also failed: {retry_err}")
            raise ValueError(f"Failed to generate valid plan after retry: {retry_err}") from retry_err

    # DB Persistence
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
        target_run_id = None
        if run_id is not None:
            if isinstance(run_id, str):
                target_run_id = uuid.UUID(run_id)
            else:
                target_run_id = run_id
            existing_run = db.query(models.Run).filter(models.Run.id == target_run_id).first()
            if not existing_run:
                run_rec = models.Run(id=target_run_id, goal_text=objective_text, status="pending")
                db.add(run_rec)
                db.commit()
                db.refresh(run_rec)
        else:
            run_rec = models.Run(goal_text=objective_text, status="pending")
            db.add(run_rec)
            db.commit()
            db.refresh(run_rec)
            target_run_id = run_rec.id

        # Mark existing plans for this run as inactive
        db.query(models.Plan).filter(
            models.Plan.run_id == target_run_id,
            models.Plan.is_current == True,
        ).update({"is_current": False})

        # Create new plan
        new_plan = models.Plan(
            run_id=target_run_id,
            is_current=True,
        )
        db.add(new_plan)
        db.commit()
        db.refresh(new_plan)

        # Create steps
        for step_data in validated_steps:
            step_obj = models.Step(
                plan_id=new_plan.id,
                description=step_data.description,
                intended_tool=step_data.intended_tool,
                status="pending",
            )
            db.add(step_obj)

        db.commit()
        db.refresh(new_plan)
        _ = new_plan.steps  # Access steps relationship to trigger loading before return

        event_emitter.emit(
            run_id=target_run_id,
            event_type=EVENT_PLAN_CREATED,
            payload={
                "plan_id": str(new_plan.id),
                "steps": [
                    {
                        "id": str(s.id),
                        "description": s.description,
                        "intended_tool": s.intended_tool,
                        "status": s.status,
                    }
                    for s in new_plan.steps
                ],
                "total_steps": len(new_plan.steps),
            },
        )

        return new_plan

    finally:
        if own_db and db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass
