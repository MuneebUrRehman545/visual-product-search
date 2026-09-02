"""Vision Integration Adapter for Week 4 Multi-Agent Integration.

Orchestrates visual search execution and shared PostgreSQL database handoff:
1. Verifies shared database connectivity and parent pipeline run existence.
2. Records execution lifecycle audit events ('started', 'completed', 'failed').
3. Records query image assets in shared database.
4. Executes CLIP / ResNet similarity search using singleton search services.
5. Persists structured product candidate matches to extracted_data for downstream RAG consumption.
6. Returns standardized VisionProcessResponse contract.
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from PIL import Image

from app.db.shared_database import (
    check_pipeline_run_exists,
    insert_asset,
    insert_extracted_data,
    insert_module_event,
    is_shared_db_configured,
)
from app.schemas.vision_pipeline import VisionMatchItem, VisionProcessResponse
from app.services.search_service_registry import (
    get_resnet_search_service,
    get_search_service,
)

logger = logging.getLogger("vision.integration.adapter")


def process_vision_request(
    query_image: Image.Image,
    pipeline_run_id: str,
    filename: Optional[str] = "query.jpg",
    mime_type: Optional[str] = "image/jpeg",
    top_k: int = 10,
    model: str = "clip",
) -> VisionProcessResponse:
    """Execute visual search pipeline and persist artifacts to shared database.

    Args:
        query_image: Decoded RGB PIL image.
        pipeline_run_id: Orchestrator-assigned pipeline run UUID string.
        filename: Optional uploaded file name.
        mime_type: Optional uploaded file MIME type.
        top_k: Number of candidate products to retrieve (1-50).
        model: Canonical model identifier ('clip' or 'resnet').

    Returns:
        VisionProcessResponse: Standardized contract response.
    """
    # 1. Require Shared Database Configuration
    if not is_shared_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shared integration database is not configured. SHARED_DATABASE_URL environment variable is missing or invalid.",
        )

    # 2. Verify pipeline_run_id exists in shared pipeline_runs table
    try:
        exists = check_pipeline_run_exists(pipeline_run_id)
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"pipeline_run_id '{pipeline_run_id}' not found in shared pipeline_runs table.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify pipeline run in shared database: {str(e)}",
        )

    # 3. Record started event & query asset in shared database
    insert_module_event(
        pipeline_run_id=pipeline_run_id,
        event="started",
        message="Visual search started.",
    )
    safe_fn = filename or "query.jpg"
    safe_mt = mime_type or "image/jpeg"
    try:
        asset_id = insert_asset(
            pipeline_run_id=pipeline_run_id,
            filename=safe_fn,
            mime_type=safe_mt,
            storage_uri=f"assets/{safe_fn}",
        )
    except Exception as e:
        insert_module_event(pipeline_run_id, "failed", f"Failed to persist asset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record query asset in shared database: {str(e)}",
        )

    # 4. Execute visual search using existing CLIP / ResNet services
    clean_model = (model or "clip").lower().strip()
    if clean_model == "resnet":
        service = get_resnet_search_service()
        model_used = "ResNet_50"
    else:
        service = get_search_service()
        model_used = "OpenCLIP_ViT_B_32"

    try:
        raw_results = service.search(query_image, top_k=top_k)
    except Exception as e:
        insert_module_event(pipeline_run_id, "failed", f"Visual search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Visual search processing error ({model_used}): {str(e)}",
        )

    matches: List[VisionMatchItem] = []
    for item in raw_results:
        fn = item.get("filename") or f"{item.get('image_id')}.jpg"
        img_url = item.get("image_url") or f"/catalog-images/{fn}"
        matches.append(
            VisionMatchItem(
                rank=item["rank"],
                catalog_item_id=int(item["catalog_item_id"]),
                product_id=int(item["product_id"]),
                external_id=str(item.get("external_id") or item["product_id"]),
                filename=fn,
                product_display_name=item.get("product_display_name"),
                category=item.get("category"),
                sub_category=item.get("sub_category"),
                article_type=item.get("article_type"),
                base_colour=item.get("base_colour"),
                gender=item.get("gender"),
                season=item.get("season"),
                usage=item.get("usage"),
                image_url=img_url,
                similarity_score=float(item["similarity_score"]),
            )
        )

    if not matches:
        insert_module_event(pipeline_run_id, "failed", "No matching products found in catalog.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No matching products found in catalog.",
        )

    primary_match = matches[0]
    confidence = float(primary_match.similarity_score)

    # 5. Persist extracted_data and completed event
    content_payload = {
        "primary_match": primary_match.model_dump(),
        "matches": [m.model_dump() for m in matches],
    }
    try:
        extracted_data_id = insert_extracted_data(
            pipeline_run_id=pipeline_run_id,
            asset_id=asset_id,
            content=content_payload,
            model=model_used,
            confidence=confidence,
        )
    except Exception as e:
        insert_module_event(pipeline_run_id, "failed", f"Failed to persist extracted data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record extracted data in shared database: {str(e)}",
        )

    insert_module_event(
        pipeline_run_id=pipeline_run_id,
        event="completed",
        message="Visual search completed.",
    )

    return VisionProcessResponse(
        pipeline_run_id=pipeline_run_id,
        status="completed",
        primary_match=primary_match,
        matches=matches,
        confidence=confidence,
        extracted_data_id=extracted_data_id,
    )
