"""Pydantic schemas for visual product search API."""

from typing import List, Optional
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """Schema for individual ranked product search result."""

    rank: int = Field(..., description="1-based rank position of similarity")
    catalog_item_id: int = Field(..., description="Catalog item primary key ID (stable database ID)")
    product_id: int = Field(..., description="Source dataset product identifier")
    external_id: Optional[str] = Field(None, description="Unique external product identifier")
    filename: str = Field(..., description="Catalog image filename")
    product_display_name: Optional[str] = Field(None, description="Product display name / title")
    category: Optional[str] = Field(None, description="Product master category")
    sub_category: Optional[str] = Field(None, description="Product sub category")
    article_type: Optional[str] = Field(None, description="Article type")
    base_colour: Optional[str] = Field(None, description="Base colour")
    gender: Optional[str] = Field(None, description="Target gender")
    season: Optional[str] = Field(None, description="Season")
    usage: Optional[str] = Field(None, description="Usage category")
    image_url: str = Field(..., description="Frontend-accessible HTTP image URL")
    similarity_score: float = Field(..., description="Similarity score (cosine or combined)")


class SearchResponse(BaseModel):
    """Schema for visual product search response."""

    query_filename: str = Field(..., description="Filename of uploaded query image")
    top_k: int = Field(..., description="Requested top_k count")
    total_results: int = Field(..., description="Number of results returned")
    model_used: Optional[str] = Field("OpenCLIP_ViT_B_32", description="Selected embedding retrieval model")
    results: List[SearchResultItem] = Field(..., description="Ranked list of search results")
