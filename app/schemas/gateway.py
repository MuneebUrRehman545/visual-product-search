"""Pydantic schemas for Week 4 Gateway -> Vision integration and run lifecycle endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.vision_pipeline import VisionMatchItem, VisionProcessResponse


class GatewayRunResponse(BaseModel):
    """Structured response returned by POST /api/v1/gateway/run upon completing Vision processing."""

    run_id: str = Field(..., description="Unique UUID identifying the execution run")
    pipeline_run_id: str = Field(..., description="Pipeline run UUID (identical to run_id)")
    status: str = Field("vision_complete", description="Current run lifecycle status (e.g. 'vision_complete')")
    primary_match: VisionMatchItem = Field(..., description="Rank-1 candidate product match")
    matches: List[VisionMatchItem] = Field(..., description="Full ranked candidate products list (1..K)")
    confidence: float = Field(..., description="Rank-1 similarity score (continuous cosine metric)")
    extracted_data_id: str = Field(..., description="UUID of the record inserted into shared extracted_data table")


class GatewayRunDetailResponse(BaseModel):
    """Detailed response returned by GET /api/v1/gateway/run/{run_id}."""

    run_id: str = Field(..., description="Unique UUID identifying the execution run")
    pipeline_run_id: str = Field(..., description="Pipeline run UUID (identical to run_id)")
    status: str = Field(..., description="Current run status (e.g. 'processing', 'vision_complete', 'failed')")
    vision_result: Optional[VisionProcessResponse] = Field(None, description="Normalized Vision output if available")
    assets: List[Dict[str, Any]] = Field(default_factory=list, description="Associated image assets")
    module_events: List[Dict[str, Any]] = Field(default_factory=list, description="Lifecycle audit log events")
    created_at: Optional[str] = Field(None, description="Run creation timestamp")
    updated_at: Optional[str] = Field(None, description="Run last updated timestamp")
