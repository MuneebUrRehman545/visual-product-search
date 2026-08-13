"""Pydantic schemas for visual product search API."""

from typing import List, Optional
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """Schema for individual ranked product search result."""

    rank: int = Field(..., description="1-based rank position of similarity")
    product_id: int = Field(..., description="SQLite primary key ID")
    external_id: str = Field(..., description="Unique external product identifier")
    filename: str = Field(..., description="Catalog image filename")
    category: Optional[str] = Field(None, description="Product category")
    image_url: str = Field(..., description="Frontend-accessible HTTP image URL")
    similarity_score: float = Field(..., description="Cosine similarity score")


class SearchResponse(BaseModel):
    """Schema for visual product search response."""

    query_filename: str = Field(..., description="Filename of uploaded query image")
    top_k: int = Field(..., description="Requested top_k count")
    total_results: int = Field(..., description="Number of results returned")
    results: List[SearchResultItem] = Field(..., description="Ranked list of search results")
