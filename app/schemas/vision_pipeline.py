"""Pydantic schemas for Week 4 Vision -> RAG integration endpoint (/api/v1/vision/process)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VisionMatchItem(BaseModel):
    """Schema for individual ranked product match in the integration contract."""

    rank: int = Field(..., description="1-based rank position")
    catalog_item_id: int = Field(..., description="Catalog database primary key ID (1:1 with FAISS index ID)")
    product_id: int = Field(..., description="Source dataset product identifier")
    external_id: Optional[str] = Field(None, description="Unique external product identifier")
    filename: str = Field(..., description="Catalog image filename")
    product_display_name: Optional[str] = Field(None, description="Product display name")
    category: Optional[str] = Field(None, description="Product category")
    sub_category: Optional[str] = Field(None, description="Product sub category")
    article_type: Optional[str] = Field(None, description="Article type")
    base_colour: Optional[str] = Field(None, description="Base colour")
    gender: Optional[str] = Field(None, description="Target demographic / gender")
    season: Optional[str] = Field(None, description="Season")
    usage: Optional[str] = Field(None, description="Usage classification")
    image_url: str = Field(..., description="URL path to access catalog image")
    similarity_score: float = Field(..., description="Inner-product cosine similarity score")


class VisionProcessResponse(BaseModel):
    """Standardized successful response schema for POST /api/v1/vision/process."""

    pipeline_run_id: str = Field(..., description="UUID of the parent pipeline run supplied by orchestrator")
    status: str = Field("completed", description="Execution status: 'completed'")
    primary_match: VisionMatchItem = Field(..., description="The Rank-1 candidate product match")
    matches: List[VisionMatchItem] = Field(..., description="Full ranked candidate products list (1..K)")
    confidence: float = Field(..., description="Rank-1 similarity score (continuous ranking metric, not probability)")
    extracted_data_id: str = Field(..., description="UUID of the record inserted into shared extracted_data table")
