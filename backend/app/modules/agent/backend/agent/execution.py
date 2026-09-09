import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy.orm import Session

import models
from agent.context import build_context_summary
from agent.events import (
    EVENT_OBSERVATION_MADE,
    EVENT_STEP_COMPLETED,
    EVENT_STEP_STARTED,
    EVENT_TOOL_CALL_RESULT,
    EVENT_TOOL_CALL_STARTED,
    event_emitter,
)
from agent.evaluator import classify_observation
from agent.llm_client import LLMClient, LLMClientError
from agent.tools import default_registry
from agent.tools.base import ToolResult
from agent.tools.registry import ToolRegistry
from database import get_db

logger = logging.getLogger(__name__)


def execute_step(
    step: Union[models.Step, str, uuid.UUID],
    db: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    registry: Optional[ToolRegistry] = None,
    run_id: Optional[Union[str, uuid.UUID]] = None,
    reformulation_hint: Optional[str] = None,
) -> ToolResult:
    """Executes a single plan step by asking the LLM to select a registered tool and arguments,
    dispatching the tool execution via the registry, saving the ToolCall to the database,
    logging step start/finish timestamps and observations, and returning the ToolResult.

    :param step: Step ORM instance or Step UUID/string ID.
    :param db: Optional SQLAlchemy session.
    :param llm_client: Optional LLMClient instance.
    :param registry: Optional ToolRegistry instance (defaults to default_registry).
    :param run_id: Optional Run UUID or string ID.
    :param reformulation_hint: Optional guidance string for self-correction retries.
    :return: ToolResult
    """
    if registry is None:
        registry = default_registry

    if llm_client is None:
        llm_client = LLMClient()

    own_db = False
    db_gen = None

    if db is None:
        try:
            from main import app
            db_provider = app.dependency_overrides.get(get_db, get_db)
        except Exception:
            db_provider = get_db

        db_gen = db_provider()
        db = next(db_gen)
        own_db = True

    try:
        # Resolve step ORM object
        step_obj: Optional[models.Step] = None
        if isinstance(step, (str, uuid.UUID)):
            step_id_val = uuid.UUID(str(step))
            step_obj = db.query(models.Step).filter(models.Step.id == step_id_val).first()
            if not step_obj:
                msg = f"Step with ID '{step}' not found in database."
                logger.error(msg)
                return ToolResult(success=False, error_message=msg)
        elif isinstance(step, models.Step):
            step_obj = step
            if db:
                step_obj = db.merge(step_obj)
        else:
            msg = f"Invalid step parameter type: {type(step)}"
            logger.error(msg)
            return ToolResult(success=False, error_message=msg)

        # Mark step as started in database immediately
        step_obj.status = "in_progress"
        step_obj.started_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(step_obj)

        # Extract effective run_id for context assembly and tools requiring per-run storage context
        effective_run_id: Optional[str] = str(run_id) if run_id is not None else None
        if effective_run_id is None and hasattr(step_obj, "plan") and step_obj.plan:
            effective_run_id = str(step_obj.plan.run_id)
        elif effective_run_id is None and step_obj.plan_id and db:
            plan_obj = db.query(models.Plan).filter(models.Plan.id == step_obj.plan_id).first()
            if plan_obj:
                effective_run_id = str(plan_obj.run_id)

        if effective_run_id:
            event_emitter.emit(
                run_id=effective_run_id,
                event_type=EVENT_STEP_STARTED,
                payload={
                    "step_id": str(step_obj.id),
                    "plan_id": str(step_obj.plan_id),
                    "description": step_obj.description,
                    "intended_tool": step_obj.intended_tool,
                    "started_at": step_obj.started_at.isoformat() if step_obj.started_at else None,
                },
            )

        # Build context summary from prior completed steps in this run
        context_summary = ""
        if effective_run_id:
            context_summary = build_context_summary(effective_run_id, db=db)

        registered_tools = registry.list_tools()
        chosen_tool_name: str
        chosen_args: dict

        try:
            chosen_tool_name, chosen_args = llm_client.decide_tool_call(
                step_description=step_obj.description,
                tools_list=registered_tools,
                context_summary=context_summary,
                reformulation_hint=reformulation_hint,
                intended_tool=step_obj.intended_tool,
            )
        except Exception as llm_err:
            logger.warning(f"LLM tool selection failed for step {step_obj.id}: {llm_err}")
            # If step has intended_tool, use it as fallback name for dispatch attempt
            chosen_tool_name = step_obj.intended_tool or "unknown"
            if chosen_tool_name == "file_read_write":
                desc_lower = (step_obj.description or "").lower()
                if any(w in desc_lower for w in ("write", "save", "create", "store")):
                    chosen_tool_name = "file_write"
                else:
                    chosen_tool_name = "file_read"
            chosen_args = {}

            if effective_run_id:
                event_emitter.emit(
                    run_id=effective_run_id,
                    event_type=EVENT_TOOL_CALL_STARTED,
                    payload={
                        "step_id": str(step_obj.id),
                        "tool_name": chosen_tool_name,
                        "input_args": chosen_args,
                    },
                )

            # If chosen_tool_name is not registered or LLM failed, dispatch will catch it or we handle graceful failure
            result = registry.dispatch(chosen_tool_name, chosen_args, run_id=effective_run_id)
            if result.success is False and "is not registered" in (result.error_message or ""):
                result.error_message = f"LLM failed to select tool: {str(llm_err)}"
            _record_tool_call(db, step_obj, chosen_tool_name, chosen_args, result, llm_client=llm_client, run_id=effective_run_id)
            return result

        if effective_run_id:
            event_emitter.emit(
                run_id=effective_run_id,
                event_type=EVENT_TOOL_CALL_STARTED,
                payload={
                    "step_id": str(step_obj.id),
                    "tool_name": chosen_tool_name,
                    "input_args": chosen_args,
                },
            )

        # Dispatch execution safely (registry handles unregistered tool name or crashes)
        result = registry.dispatch(chosen_tool_name, chosen_args, run_id=effective_run_id)

        # Record tool call, observation, and complete step in DB
        _record_tool_call(db, step_obj, chosen_tool_name, chosen_args, result, llm_client=llm_client, run_id=effective_run_id)

        return result

    except Exception as exc:
        step_obj.status = "failed"
        step_obj.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise exc

    finally:
        if own_db and db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass


def _record_tool_call(
    db: Session,
    step_obj: models.Step,
    tool_name: str,
    input_args: dict,
    result: ToolResult,
    llm_client: Optional[LLMClient] = None,
    run_id: Optional[Union[str, uuid.UUID]] = None,
) -> models.ToolCall:
    """Helper to save ToolCall record, Observation record, and update Step status & completed_at in database."""
    output_data = None
    if result.data is not None:
        if isinstance(result.data, dict):
            output_data = result.data
        else:
            output_data = {"result": result.data}

    effective_run_id = str(run_id) if run_id else None
    if not effective_run_id and step_obj.plan:
        effective_run_id = str(step_obj.plan.run_id)

    # 1. Save tool_calls row
    tool_call = models.ToolCall(
        step_id=step_obj.id,
        tool_name=tool_name,
        input_args=input_args if isinstance(input_args, dict) else {"raw": str(input_args)},
        output_data=output_data,
        success=result.success,
        error_message=result.error_message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tool_call)
    db.commit()
    db.refresh(tool_call)

    if effective_run_id:
        event_emitter.emit(
            run_id=effective_run_id,
            event_type=EVENT_TOOL_CALL_RESULT,
            payload={
                "step_id": str(step_obj.id),
                "tool_call_id": str(tool_call.id),
                "tool_name": tool_name,
                "input_args": tool_call.input_args,
                "output_data": tool_call.output_data,
                "success": result.success,
                "error_message": result.error_message,
            },
        )

    # 2. Save/Update real observation using evaluator
    obs_res = classify_observation(
        step=step_obj,
        tool_result=result,
        llm_client=llm_client,
        db=db,
    )

    if effective_run_id:
        event_emitter.emit(
            run_id=effective_run_id,
            event_type=EVENT_OBSERVATION_MADE,
            payload={
                "step_id": str(step_obj.id),
                "classification": obs_res.classification,
                "recommendation": obs_res.recommendation,
                "reasoning": obs_res.reasoning,
            },
        )

    # 3. Update step status and completed_at
    step_obj.status = "completed" if result.success else "failed"
    step_obj.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(step_obj)

    if effective_run_id:
        event_emitter.emit(
            run_id=effective_run_id,
            event_type=EVENT_STEP_COMPLETED,
            payload={
                "step_id": str(step_obj.id),
                "status": step_obj.status,
                "result_ref": step_obj.result_ref,
                "completed_at": step_obj.completed_at.isoformat() if step_obj.completed_at else None,
            },
        )

    return tool_call
