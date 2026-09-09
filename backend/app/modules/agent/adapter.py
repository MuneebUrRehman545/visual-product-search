import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session

# Ensure backend/app/modules/agent/backend is on sys.path to resolve existing agent orchestrator modules
AGENT_BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(AGENT_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_BACKEND_DIR))

# Ensure root paths are available for schema contracts
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from backend.app.gateway.database import SessionLocal
    from backend.app.gateway import models
    from backend.app.gateway.service import update_pipeline_status
    from backend.app.schemas.contracts import AgentDecision, AgentRunResponse, PipelineStatus
except ImportError:
    try:
        from app.gateway.database import SessionLocal
        from app.gateway import models
        from app.gateway.service import update_pipeline_status
        from app.schemas.contracts import AgentDecision, AgentRunResponse, PipelineStatus
    except ImportError:
        from gateway.database import SessionLocal
        from gateway import models
        from gateway.service import update_pipeline_status
        from schemas.contracts import AgentDecision, AgentRunResponse, PipelineStatus

# Locate and import existing agent orchestrator logic (without modifying its internals)
try:
    from agent.orchestrator import run_agent as orchestrator_run_agent, synthesize_report
    import models as agent_models
except ImportError:
    try:
        from backend.app.modules.agent.backend.agent.orchestrator import (
            run_agent as orchestrator_run_agent,
            synthesize_report,
        )
        from backend.app.modules.agent.backend import models as agent_models
    except ImportError:
        orchestrator_run_agent = None
        synthesize_report = None
        agent_models = None

logger = logging.getLogger(__name__)

# Minimum similarity/confidence threshold for a confident Vision match
VISION_CONFIDENCE_THRESHOLD = 0.70


def get_vision_result(pipeline_run_id: str, db: Optional[Session] = None) -> Optional[dict]:
    """
    Fetch Vision module output/state from shared DB for given pipeline_run_id.
    Queries pipeline_runs and extracted_data tables via gateway database session.
    Checks BOTH status and presence of real result data.
    Maps to what apply_decision_rules() expects: confidence, similarity_score, is_confident.
    """
    logger.info(f"Fetching vision result for pipeline_run_id: {pipeline_run_id}")
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.id == pipeline_run_id).first()
        if not run:
            logger.warning(f"Pipeline run '{pipeline_run_id}' not found in pipeline_runs.")
            return None

        # Guard against explicit failure state
        if run.status in [PipelineStatus.VISION_FAILED.value, PipelineStatus.FAILED.value]:
            logger.warning(f"Pipeline run '{pipeline_run_id}' has failure status: {run.status}")
            return None

        # Check presence of real result data in extracted_data
        extracted = (
            db.query(models.ExtractedData)
            .filter(models.ExtractedData.pipeline_run_id == pipeline_run_id)
            .order_by(models.ExtractedData.created_at.desc())
            .first()
        )
        if not extracted or not extracted.content:
            logger.warning(f"No extracted_data found for pipeline_run_id: {pipeline_run_id}")
            return None

        content = extracted.content or {}
        primary_match = content.get("primary_match") or {}
        similarity_score = primary_match.get("similarity_score")
        confidence = extracted.confidence

        if similarity_score is None and confidence is not None:
            similarity_score = float(confidence)
        if confidence is None and similarity_score is not None:
            confidence = float(similarity_score)

        conf_val = float(confidence) if confidence is not None else 0.0
        sim_val = float(similarity_score) if similarity_score is not None else 0.0
        is_confident = (conf_val >= VISION_CONFIDENCE_THRESHOLD) and (sim_val >= VISION_CONFIDENCE_THRESHOLD)

        return {
            "extracted_data_id": str(extracted.id),
            "confidence": conf_val,
            "similarity_score": sim_val,
            "is_confident": is_confident,
            "primary_match": primary_match,
            "content": content,
            "model": extracted.model,
        }
    except Exception as exc:
        logger.error(f"Error fetching vision result for {pipeline_run_id}: {exc}", exc_info=True)
        return None
    finally:
        if should_close:
            db.close()


def get_rag_result(pipeline_run_id: str, db: Optional[Session] = None) -> Optional[dict]:
    """
    Fetch RAG module output/state from shared DB for given pipeline_run_id.
    Queries pipeline_runs and rag_documents tables via gateway database session.
    Checks BOTH status and presence of real result data.
    Maps to what is_rag_grounded_and_complete() expects: grounded, complete, citations.
    Treats explicit no-answer ("couldn't find...") as NOT grounded.
    """
    logger.info(f"Fetching RAG result for pipeline_run_id: {pipeline_run_id}")
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.id == pipeline_run_id).first()
        if not run:
            logger.warning(f"Pipeline run '{pipeline_run_id}' not found in pipeline_runs.")
            return None

        # Guard against explicit failure state
        if run.status in [PipelineStatus.RAG_FAILED.value, PipelineStatus.FAILED.value]:
            logger.warning(f"Pipeline run '{pipeline_run_id}' has failure status: {run.status}")
            return None

        # Check presence of real result data in rag_documents
        rag_doc = (
            db.query(models.RagDocument)
            .filter(models.RagDocument.pipeline_run_id == pipeline_run_id)
            .order_by(models.RagDocument.created_at.desc())
            .first()
        )
        if not rag_doc or not rag_doc.content:
            logger.warning(f"No rag_documents found for pipeline_run_id: {pipeline_run_id}")
            return None

        content = rag_doc.content.strip()
        metadata = rag_doc.metadata_json or {}

        # Detect explicit no-answer / ungrounded responses
        lower_content = content.lower()
        no_answer_patterns = [
            "couldn't find",
            "could not find",
            "cannot find",
            "not found in the uploaded",
            "no information found",
            "unable to find",
        ]
        is_explicit_no_answer = any(pat in lower_content for pat in no_answer_patterns)

        if is_explicit_no_answer:
            grounded = False
        else:
            raw_grounded = metadata.get("grounded", True)
            grounded = bool(raw_grounded)

        status_val = metadata.get("status", "completed")
        complete = status_val == "completed" or (
            run.status in [
                PipelineStatus.RAG_COMPLETE.value,
                PipelineStatus.AGENT_PROCESSING.value,
                PipelineStatus.AGENT_COMPLETE.value,
                PipelineStatus.COMPLETED.value,
            ]
        )

        citations = metadata.get("citations") or []

        return {
            "rag_document_id": str(rag_doc.id),
            "content": content,
            "grounded": grounded,
            "is_grounded": grounded,
            "complete": complete,
            "is_complete": complete,
            "citations": citations,
            "metadata": metadata,
        }
    except Exception as exc:
        logger.error(f"Error fetching RAG result for {pipeline_run_id}: {exc}", exc_info=True)
        return None
    finally:
        if should_close:
            db.close()


def is_vision_confident(vision_data: dict) -> bool:
    """Helper to check if Vision match meets confidence criteria."""
    if vision_data.get("is_confident") is False:
        return False
    if vision_data.get("weak_match") is True:
        return False
    if "similarity_score" in vision_data and vision_data["similarity_score"] < VISION_CONFIDENCE_THRESHOLD:
        return False
    if "confidence" in vision_data and vision_data["confidence"] < VISION_CONFIDENCE_THRESHOLD:
        return False
    if "similarity" in vision_data and vision_data["similarity"] < VISION_CONFIDENCE_THRESHOLD:
        return False
    return True


def is_rag_grounded_and_complete(rag_data: dict) -> bool:
    """Helper to check if RAG context is grounded and sufficiently cited/complete."""
    if rag_data.get("grounded") is False or rag_data.get("is_grounded") is False:
        return False
    if rag_data.get("complete") is False or rag_data.get("is_complete") is False:
        return False
    if rag_data.get("thin_citations") is True:
        return False
    if "citations" in rag_data and len(rag_data["citations"]) == 0 and rag_data.get("requires_citations", False):
        return False

    content = (rag_data.get("content") or "").lower()
    no_answer_patterns = [
        "couldn't find",
        "could not find",
        "cannot find",
        "not found in the uploaded",
        "no information found",
        "unable to find",
    ]
    if any(pat in content for pat in no_answer_patterns):
        return False

    return True


def apply_decision_rules(
    vision_data: Optional[dict],
    rag_data: Optional[dict],
) -> Tuple[AgentDecision, str]:
    """
    Apply decision rules mapping Vision & RAG state to AgentDecision:
    - Vision or RAG state missing entirely -> flag_incomplete
    - Vision match weak/below similarity threshold -> needs_review
    - Confident Vision match + RAG present but not grounded / thin citations -> search_more_context
    - Confident Vision match + RAG grounded, complete -> generate_report
    """
    # 1. State missing entirely
    if vision_data is None or rag_data is None:
        return (
            AgentDecision.flag_incomplete,
            "Vision or RAG state missing entirely.",
        )

    # 2. Vision match weak / below similarity threshold
    if not is_vision_confident(vision_data):
        return (
            AgentDecision.needs_review,
            "Vision match weak or below similarity threshold.",
        )

    # 3. Confident Vision match + RAG present but not grounded / thin citations
    if not is_rag_grounded_and_complete(rag_data):
        # Check if grounded is True but citations are thin
        is_grounded = rag_data.get("grounded") is True or rag_data.get("is_grounded") is True
        content = (rag_data.get("content") or "").lower()
        no_answer_patterns = [
            "couldn't find",
            "could not find",
            "cannot find",
            "not found in the uploaded",
            "no information found",
            "unable to find",
        ]
        if any(pat in content for pat in no_answer_patterns):
            is_grounded = False

        is_thin_citations = (
            rag_data.get("thin_citations") is True
            or (isinstance(rag_data.get("citations"), list) and len(rag_data.get("citations")) == 0)
            or bool(rag_data.get("thin_citations"))
            or rag_data.get("citation_count") == 0
        )

        if is_grounded and is_thin_citations:
            reason = "RAG context is grounded but has thin citation coverage."
        else:
            reason = "Confident Vision match, but RAG context is not grounded or has thin citations."

        return (
            AgentDecision.search_more_context,
            reason,
        )

    # 4. Confident Vision match + RAG grounded, complete
    return (
        AgentDecision.generate_report,
        "Confident Vision match and RAG retrieved context is grounded and complete.",
    )


async def run_agent(pipeline_run_id: str, db: Optional[Session] = None) -> AgentRunResponse:
    """
    Main Agent execution adapter:
    1. Sets pipeline status to agent_processing and broadcasts live WebSocket event.
    2. Fetches Vision and RAG state for pipeline_run_id from shared DB.
    3. Flags incomplete if either is missing.
    4. Applies decision rules.
    5. Persists agent execution summary and granular actions into agent_runs and agent_actions.
    6. Updates pipeline_runs.status to agent_complete, logs module_events, and broadcasts live WebSocket event.
    7. Returns unified AgentRunResponse.
    """
    agent_run_id = str(uuid.uuid4())
    actions: list[dict] = []

    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        # 1. Update status to agent_processing and broadcast over WebSocket
        update_pipeline_status(
            db=db,
            pipeline_run_id=pipeline_run_id,
            new_status=PipelineStatus.AGENT_PROCESSING,
            module="agent",
            message="Agent processing initiated.",
            payload={"pipeline_run_id": pipeline_run_id},
        )
        await asyncio.sleep(0.05)

        # 2. Fetch upstream module outputs from shared DB
        vision_data = get_vision_result(pipeline_run_id, db=db)
        rag_data = get_rag_result(pipeline_run_id, db=db)

        # 3. Apply Decision Rules
        decision, reason = apply_decision_rules(vision_data, rag_data)

        actions.append({
            "action_type": "decision_rule_evaluation",
            "payload": {
                "pipeline_run_id": pipeline_run_id,
                "decision": decision.value,
                "reason": reason,
                "has_vision_data": vision_data is not None,
                "has_rag_data": rag_data is not None,
            },
        })

        # 4. Determine status and dispatch downstream actions
        status_str = "completed"
        if decision == AgentDecision.flag_incomplete:
            status_str = "flagged_incomplete"
        elif decision == AgentDecision.needs_review:
            status_str = "pending_review"
        elif decision == AgentDecision.search_more_context:
            status_str = "in_progress"
            actions.append({
                "action_type": "search_more_context_dispatched",
                "payload": {
                    "pipeline_run_id": pipeline_run_id,
                    "status": "search_dispatched",
                },
            })
        elif decision == AgentDecision.generate_report:
            status_str = "completed"
            if orchestrator_run_agent is not None:
                actions.append({
                    "action_type": "orchestrator_invoked",
                    "payload": {
                        "module": "backend.app.modules.agent.backend.agent.orchestrator",
                        "status": "report_generation_ready",
                    },
                })

        # 5. Persist to shared database: agent_runs and agent_actions
        now = datetime.now(timezone.utc)
        agent_run_record = models.AgentRun(
            agent_run_id=agent_run_id,
            pipeline_run_id=pipeline_run_id,
            status=status_str,
            decision=decision.value,
            reason=reason,
            created_at=now,
            completed_at=now if status_str == "completed" else None,
        )
        db.add(agent_run_record)

        for act in actions:
            action_record = models.AgentAction(
                id=str(uuid.uuid4()),
                agent_run_id=agent_run_id,
                action_type=act["action_type"],
                payload=act["payload"],
                created_at=now,
            )
            db.add(action_record)

        db.commit()

        # 6. Update pipeline run status, persist module_event, and broadcast over WebSocket
        if decision in {
            AgentDecision.generate_report,
            AgentDecision.needs_review,
            AgentDecision.flag_incomplete,
        }:
            target_pipeline_status = PipelineStatus.AGENT_COMPLETE
        elif decision == AgentDecision.search_more_context:
            target_pipeline_status = PipelineStatus.AGENT_PROCESSING

        update_pipeline_status(
            db=db,
            pipeline_run_id=pipeline_run_id,
            new_status=target_pipeline_status,
            module="agent",
            message=f"Agent decision reached: {decision.value}. {reason}",
            payload={
                "agent_run_id": agent_run_id,
                "decision": decision.value,
                "reason": reason,
                "status": status_str,
            },
        )
        await asyncio.sleep(0.05)

    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to execute agent run for {pipeline_run_id}: {exc}", exc_info=True)
        try:
            update_pipeline_status(
                db=db,
                pipeline_run_id=pipeline_run_id,
                new_status=PipelineStatus.AGENT_FAILED,
                module="agent",
                message=f"Agent execution failed: {str(exc)}",
                payload={"error": str(exc)},
            )
        except Exception:
            pass
        raise
    finally:
        if should_close:
            db.close()

    return AgentRunResponse(
        pipeline_run_id=pipeline_run_id,
        agent_run_id=agent_run_id,
        status=status_str,
        decision=decision,
        reason=reason,
        actions=actions,
    )
