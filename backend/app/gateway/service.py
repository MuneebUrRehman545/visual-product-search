import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

try:
    from backend.app.gateway import models
    from backend.app.gateway.events import (
        EVENT_RUN_CREATED,
        EVENT_STATUS_UPDATED,
        pipeline_event_emitter,
    )
    from backend.app.schemas.contracts import (
        PipelineRunStatusResponse,
        PipelineStatus,
    )
except ImportError:
    from app.gateway import models
    from app.gateway.events import (
        EVENT_RUN_CREATED,
        EVENT_STATUS_UPDATED,
        pipeline_event_emitter,
    )
    from app.schemas.contracts import (
        PipelineRunStatusResponse,
        PipelineStatus,
    )

logger = logging.getLogger(__name__)


def create_pipeline_run(
    db: Session,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> models.PipelineRun:
    """
    Creates a new pipeline run, writes an initial row to the shared pipeline_runs table,
    logs the creation event in module_events, and emits a live status update.
    """
    run_id = str(uuid.uuid4())
    initial_status = PipelineStatus.CREATED.value
    now = datetime.now(timezone.utc)

    # 1. Create pipeline_runs record
    pipeline_run = models.PipelineRun(
        id=run_id,
        status=initial_status,
        created_at=now,
        updated_at=now,
    )
    db.add(pipeline_run)

    # 2. Add audit log to module_events
    creation_event = models.ModuleEvent(
        id=str(uuid.uuid4()),
        pipeline_run_id=run_id,
        module="gateway",
        event="created",
        message="Pipeline run initialized.",
        payload={"user_id": user_id, "metadata": metadata or {}},
        created_at=now,
    )
    db.add(creation_event)

    db.commit()
    db.refresh(pipeline_run)

    # 3. Broadcast creation event over WebSocket channel
    pipeline_event_emitter.emit(
        pipeline_run_id=run_id,
        event_type=EVENT_RUN_CREATED,
        payload={"user_id": user_id, "metadata": metadata or {}},
        message="Pipeline run initialized.",
        status=initial_status,
    )

    logger.info(f"Created pipeline_run_id={run_id} with status={initial_status}")
    return pipeline_run


def get_pipeline_run(db: Session, pipeline_run_id: str) -> Optional[models.PipelineRun]:
    """Retrieve raw PipelineRun model instance by ID."""
    return db.query(models.PipelineRun).filter(models.PipelineRun.id == pipeline_run_id).first()


def get_pipeline_run_status(db: Session, pipeline_run_id: str) -> Optional[PipelineRunStatusResponse]:
    """
    Constructs the unified status response for a pipeline run, aggregating available
    Vision, RAG, and Agent stage outputs from shared database tables.
    Returns None if pipeline_run_id is not found.
    """
    run = get_pipeline_run(db, pipeline_run_id)
    if not run:
        return None

    # Aggregate Vision results if available (extracted_data table)
    vision_result: Optional[Dict[str, Any]] = None
    extracted_records = (
        db.query(models.ExtractedData)
        .filter(models.ExtractedData.pipeline_run_id == pipeline_run_id)
        .order_by(models.ExtractedData.created_at.desc())
        .all()
    )
    if extracted_records:
        latest = extracted_records[0]
        vision_result = {
            "extracted_data_id": str(latest.id),
            "module": latest.module,
            "data_type": latest.data_type,
            "content": latest.content,
            "model": latest.model,
            "confidence": latest.confidence,
            "count": len(extracted_records),
        }

    # Aggregate RAG results if available (rag_documents table)
    rag_result: Optional[Dict[str, Any]] = None
    rag_records = (
        db.query(models.RagDocument)
        .filter(models.RagDocument.pipeline_run_id == pipeline_run_id)
        .order_by(models.RagDocument.created_at.desc())
        .all()
    )
    if rag_records:
        latest_rag = rag_records[0]
        rag_result = {
            "rag_document_id": str(latest_rag.id),
            "content": latest_rag.content,
            "metadata": latest_rag.metadata_json,
            "count": len(rag_records),
        }

    # Downstream Agent results
    agent_result: Optional[Dict[str, Any]] = None
    agent_record = (
        db.query(models.AgentRun)
        .filter(models.AgentRun.pipeline_run_id == pipeline_run_id)
        .order_by(models.AgentRun.created_at.desc())
        .first()
    )
    if agent_record:
        agent_result = {
            "agent_run_id": str(agent_record.agent_run_id),
            "status": agent_record.status,
            "decision": agent_record.decision,
            "reason": agent_record.reason,
            "created_at": agent_record.created_at.isoformat() if agent_record.created_at else None,
            "completed_at": agent_record.completed_at.isoformat() if agent_record.completed_at else None,
        }

    # Formulate events history
    events_list: List[Dict[str, Any]] = []
    events = (
        db.query(models.ModuleEvent)
        .filter(models.ModuleEvent.pipeline_run_id == pipeline_run_id)
        .order_by(models.ModuleEvent.created_at.asc())
        .all()
    )
    for ev in events:
        events_list.append({
            "id": str(ev.id),
            "module": ev.module,
            "event": ev.event,
            "message": ev.message,
            "payload": ev.payload,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })

    return PipelineRunStatusResponse(
        pipeline_run_id=str(run.id),
        status=PipelineStatus(run.status),
        created_at=run.created_at,
        updated_at=run.updated_at,
        vision_result=vision_result,
        rag_result=rag_result,
        agent_result=agent_result,
        events=events_list,
    )


def update_pipeline_status(
    db: Session,
    pipeline_run_id: str,
    new_status: PipelineStatus,
    module: str,
    message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[models.PipelineRun]:
    """
    Updates the pipeline status, persists a new event in module_events,
    and broadcasts the update over the WebSocket event channel.
    """
    run = get_pipeline_run(db, pipeline_run_id)
    if not run:
        return None

    now = datetime.now(timezone.utc)
    run.status = new_status.value
    run.updated_at = now

    event = models.ModuleEvent(
        id=str(uuid.uuid4()),
        pipeline_run_id=pipeline_run_id,
        module=module,
        event=new_status.value,
        message=message or f"Status updated to {new_status.value}",
        payload=payload or {},
        created_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(run)

    pipeline_event_emitter.emit(
        pipeline_run_id=pipeline_run_id,
        event_type=EVENT_STATUS_UPDATED,
        payload=payload or {},
        message=message or f"Status updated to {new_status.value}",
        status=new_status.value,
    )

    logger.info(f"Updated pipeline_run_id={pipeline_run_id} to status={new_status.value}")
    return run
