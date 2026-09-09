from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PipelineStatus(str, Enum):
    """
    Single source of truth for the end-to-end pipeline lifecycle statuses across
    Gateway, Vision, RAG, and Agent modules.
    """
    CREATED = "created"
    VISION_PROCESSING = "vision_processing"
    VISION_COMPLETE = "vision_complete"
    VISION_FAILED = "vision_failed"
    RAG_PROCESSING = "rag_processing"
    RAG_COMPLETE = "rag_complete"
    RAG_FAILED = "rag_failed"
    AGENT_PROCESSING = "agent_processing"
    AGENT_COMPLETE = "agent_complete"
    AGENT_FAILED = "agent_failed"
    COMPLETED = "completed"
    FAILED = "failed"


class ModuleEventPayload(BaseModel):
    id: Optional[str] = None
    pipeline_run_id: str
    module: str
    event: str
    message: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class PipelineRunCreateRequest(BaseModel):
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class PipelineRunCreateResponse(BaseModel):
    pipeline_run_id: str
    status: PipelineStatus
    created_at: datetime


class PipelineRunStatusResponse(BaseModel):
    pipeline_run_id: str
    status: PipelineStatus
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    vision_result: Optional[Dict[str, Any]] = None
    rag_result: Optional[Dict[str, Any]] = None
    agent_result: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = Field(default_factory=list)


class NotImplementedResponse(BaseModel):
    status: str = "not_implemented"
    message: str
    step: str
    owner: str


class AgentDecision(str, Enum):
    generate_report = "generate_report"
    search_more_context = "search_more_context"
    needs_review = "needs_review"
    flag_incomplete = "flag_incomplete"


class AgentRunRequest(BaseModel):
    pipeline_run_id: str


class AgentRunResponse(BaseModel):
    pipeline_run_id: str
    agent_run_id: str
    status: str
    decision: AgentDecision
    reason: str
    actions: list[dict] = Field(default_factory=list)

