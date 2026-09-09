import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from backend.app.gateway.database import get_db
from backend.app.gateway.events import EVENT_CATCH_UP, pipeline_event_emitter
from backend.app.gateway import service
from backend.app.schemas.contracts import (
    NotImplementedResponse,
    PipelineRunCreateRequest,
    PipelineRunCreateResponse,
    PipelineRunStatusResponse,
    PipelineStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Gateway & Pipeline Lifecycle"])


# -----------------------------------------------------------------------------
# 1. Pipeline Run Lifecycle Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/api/v1/pipeline/run",
    response_model=PipelineRunCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new end-to-end pipeline run",
)
async def create_pipeline_run_endpoint(
    request: Optional[PipelineRunCreateRequest] = None,
    db: Session = Depends(get_db),
) -> PipelineRunCreateResponse:
    """
    Creates a new pipeline run:
    - Generates a unique pipeline_run_id (UUID).
    - Inserts an initial row into the shared pipeline_runs table with status='created'.
    - Logs the initialization event in module_events.
    - Emits a run_created event on the live event stream.
    - Returns pipeline_run_id and initial status.
    """
    req_data = request or PipelineRunCreateRequest()
    try:
        run = service.create_pipeline_run(
            db=db,
            user_id=req_data.user_id,
            metadata=req_data.metadata,
        )
        return PipelineRunCreateResponse(
            pipeline_run_id=str(run.id),
            status=PipelineStatus(run.status),
            created_at=run.created_at,
        )
    except Exception as exc:
        logger.error(f"Failed to create pipeline run: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize pipeline run: {str(exc)}",
        ) from exc


@router.get(
    "/api/v1/pipeline/run/{run_id}",
    response_model=PipelineRunStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current pipeline run status and stage outputs",
)
async def get_pipeline_run_status_endpoint(
    run_id: str,
    db: Session = Depends(get_db),
) -> PipelineRunStatusResponse:
    """
    Retrieves the current execution status and any available Vision, RAG,
    or Agent stage outputs from the shared database.
    """
    status_response = service.get_pipeline_run_status(db, run_id)
    if not status_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )
    return status_response


# -----------------------------------------------------------------------------
# 2. WebSocket Event Streaming Channel
# -----------------------------------------------------------------------------

@router.websocket("/ws/pipeline/{run_id}")
async def websocket_pipeline_stream(
    websocket: WebSocket,
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    WebSocket endpoint streaming live status updates and module events for a specific pipeline run.
    Reuses the connection and pub-sub pattern from the standalone Research Agent.
    """
    await websocket.accept()

    # Verify run existence
    run_status = service.get_pipeline_run_status(db, run_id)
    if not run_status:
        await websocket.send_json({
            "type": "error",
            "event": "error",
            "pipeline_run_id": run_id,
            "message": f"Pipeline run '{run_id}' not found.",
            "payload": {"status_code": 404},
        })
        await websocket.close(code=1008)
        return

    # Send initial snapshot / catch-up state to newly connected client
    await websocket.send_json({
        "type": EVENT_CATCH_UP,
        "event": EVENT_CATCH_UP,
        "pipeline_run_id": run_id,
        "status": run_status.status.value,
        "message": "Connected to pipeline stream.",
        "payload": {
            "status": run_status.status.value,
            "created_at": run_status.created_at.isoformat() if run_status.created_at else None,
            "vision_result": run_status.vision_result,
            "rag_result": run_status.rag_result,
            "agent_result": run_status.agent_result,
            "events": run_status.events,
        },
    })

    # Subscribe to live broadcasts
    pipeline_event_emitter.subscribe(run_id, websocket)

    try:
        while True:
            # Keep connection alive; handle any client incoming messages
            data = await websocket.receive_text()
            logger.debug(f"Received message from client on pipeline ws {run_id}: {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from pipeline stream {run_id}")
    except Exception as err:
        logger.debug(f"WebSocket connection error on pipeline stream {run_id}: {err}")
    finally:
        pipeline_event_emitter.unsubscribe(run_id, websocket)


# -----------------------------------------------------------------------------
# 3. Downstream Module Route Stubs (Steps 3, 4, and 5)
# -----------------------------------------------------------------------------

# The former Vision 501 stub is intentionally disabled. The eventual mounted
# Vision router will own the Vision routes, so registering this placeholder
# would conflict with the real implementation. Keep the original stub below
# as a record of the integration point it represented.
#
# @router.post(
#     "/api/v1/vision/run",
#     response_model=NotImplementedResponse,
#     status_code=status.HTTP_501_NOT_IMPLEMENTED,
#     summary="[STUB] Step 3: Vision Module Integration",
# )
# async def vision_run_stub():
#     """Route stub for Step 3 (Vision Module Integration) owned by Muneeb."""
#     return NotImplementedResponse(
#         status="not_implemented",
#         step="Step 3 (Vision Module Integration)",
#         owner="Muneeb",
#         message="Vision module integration is pending execution by Muneeb.",
#     )


@router.post(
    "/api/v1/rag/run",
    response_model=NotImplementedResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[STUB] Step 4: RAG Module Integration",
)
async def rag_run_stub():
    """Route stub for Step 4 (RAG Module Integration) owned by Faizan."""
    return NotImplementedResponse(
        status="not_implemented",
        step="Step 4 (RAG Module Integration)",
        owner="Faizan",
        message="RAG module integration is pending execution by Faizan.",
    )


@router.post(
    "/api/v1/agent/decision",
    response_model=NotImplementedResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[STUB] Step 5: Agent Decision & Orchestration Integration",
)
async def agent_decision_stub():
    """Route stub for Step 5 (Agent Decision & Orchestration) owned by Moeez."""
    return NotImplementedResponse(
        status="not_implemented",
        step="Step 5 (Agent Decision & Orchestration)",
        owner="Moeez",
        message="Agent decision orchestration integration is blocked pending completion of Step 4 (RAG).",
    )
