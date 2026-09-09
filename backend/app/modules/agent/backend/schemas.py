import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


class RunCreate(BaseModel):
    goal_text: str

    @field_validator("goal_text")
    @classmethod
    def validate_goal_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("goal_text cannot be empty")
        return v.strip()


class ToolCallResponse(BaseModel):
    id: uuid.UUID
    step_id: uuid.UUID
    tool_name: str
    input_args: dict[str, Any]
    output_data: Optional[dict[str, Any]] = None
    success: bool
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ObservationResponse(BaseModel):
    id: uuid.UUID
    step_id: uuid.UUID
    classification: str
    recommendation: str
    reasoning: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StepResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    description: str
    intended_tool: str
    status: str
    result_ref: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tool_calls: List[ToolCallResponse] = []
    observation: Optional[ObservationResponse] = None

    model_config = {"from_attributes": True}


class PlanResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    created_at: datetime
    is_current: bool
    steps: List[StepResponse] = []

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    content_markdown: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RunResponse(BaseModel):
    id: uuid.UUID
    goal_text: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    plans: List[PlanResponse] = []
    report: Optional[ReportResponse] = None

    model_config = {"from_attributes": True}
