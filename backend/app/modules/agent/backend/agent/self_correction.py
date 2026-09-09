import logging
import uuid
from typing import Any, Dict, Optional, Tuple, Union

from sqlalchemy.orm import Session

from datetime import datetime, timezone

import models
from agent.events import EVENT_REPLAN_TRIGGERED, EVENT_STEP_COMPLETED, event_emitter
from agent.evaluator import (
    CLASSIFICATION_HARD_FAILURE,
    CLASSIFICATION_INSUFFICIENT,
    CLASSIFICATION_SUCCESS,
    CLASSIFICATION_TRANSIENT_FAILURE,
    ObservationResult,
)
from agent.llm_client import LLMClient
from agent.tools.base import ToolResult
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

ACTION_CONTINUE = "continue"
ACTION_RETRY_SAME = "retry_same"
ACTION_RETRY_REFORMULATED = "retry_reformulated"
ACTION_SKIP_AND_FLAG = "skip_and_flag"


def decide_correction(
    observation: Union[models.Observation, ObservationResult, dict, str],
    step: Optional[models.Step] = None,
    retry_count: int = 0,
) -> str:
    """Maps an observation classification to a self-correction action:

    - "success" -> "continue" (move to next planned step)
    - "insufficient" -> "retry_reformulated" (capped at 1 retry before falling back to skip_and_flag)
    - "transient_failure" -> "retry_same" (capped at 1 retry before falling back to skip_and_flag)
    - "hard_failure" -> "skip_and_flag" (mark step skipped, record why, move on without retrying)
    """
    if isinstance(observation, str):
        classification = observation.strip().lower()
    elif isinstance(observation, (models.Observation, ObservationResult)):
        classification = str(observation.classification or "").strip().lower()
    elif isinstance(observation, dict):
        classification = str(observation.get("classification", "")).strip().lower()
    else:
        classification = "success"

    if classification == CLASSIFICATION_SUCCESS:
        return ACTION_CONTINUE

    elif classification == CLASSIFICATION_INSUFFICIENT:
        if retry_count < 1:
            return ACTION_RETRY_REFORMULATED
        return ACTION_SKIP_AND_FLAG

    elif classification == CLASSIFICATION_TRANSIENT_FAILURE:
        if retry_count < 1:
            return ACTION_RETRY_SAME
        return ACTION_SKIP_AND_FLAG

    elif classification == CLASSIFICATION_HARD_FAILURE:
        return ACTION_SKIP_AND_FLAG

    # Unknown classification default
    return ACTION_CONTINUE


def apply_self_correction(
    step: models.Step,
    observation: Union[models.Observation, ObservationResult],
    retry_count: int,
    db: Session,
    llm_client: Optional[LLMClient] = None,
    registry: Optional[ToolRegistry] = None,
    run_id: Optional[Union[str, uuid.UUID]] = None,
) -> Tuple[str, Optional[ToolResult]]:
    """Applies the decided self-correction action to the step and plan.
    Emits log and console messages, mutates the database state, and executes retries if applicable.
    """
    action = decide_correction(observation, step=step, retry_count=retry_count)
    reasoning = getattr(observation, "reasoning", "") or ""
    classification = getattr(observation, "classification", "") or ""

    if action == ACTION_CONTINUE:
        return ACTION_CONTINUE, None

    elif action == ACTION_RETRY_SAME:
        msg = (
            f"Step '{step.description}' failed with transient failure ({reasoning}) – "
            f"retrying step with same arguments (retry {retry_count + 1}/1)."
        )
        logger.info(msg)
        print(f"\n[Agent Self-Correction] {msg}")

        if run_id:
            event_emitter.emit(
                run_id=run_id,
                event_type=EVENT_REPLAN_TRIGGERED,
                payload={
                    "step_id": str(step.id),
                    "action": ACTION_RETRY_SAME,
                    "retry_count": retry_count + 1,
                    "reasoning": reasoning,
                    "message": msg,
                },
            )

        from agent.execution import execute_step
        retry_result = execute_step(
            step=step,
            db=db,
            llm_client=llm_client,
            registry=registry,
            run_id=run_id,
        )
        return ACTION_RETRY_SAME, retry_result

    elif action == ACTION_RETRY_REFORMULATED:
        msg = (
            f"Step '{step.description}' yielded insufficient results ({reasoning}) – "
            f"reformulating query and retrying (retry {retry_count + 1}/1)."
        )
        logger.info(msg)
        print(f"\n[Agent Self-Correction] {msg}")

        if run_id:
            event_emitter.emit(
                run_id=run_id,
                event_type=EVENT_REPLAN_TRIGGERED,
                payload={
                    "step_id": str(step.id),
                    "action": ACTION_RETRY_REFORMULATED,
                    "retry_count": retry_count + 1,
                    "reasoning": reasoning,
                    "message": msg,
                },
            )

        from agent.execution import execute_step
        reformulation_hint = (
            f"Previous attempt was insufficient ({reasoning}). "
            f"Please choose alternative or reworded tool arguments to better answer this step."
        )
        retry_result = execute_step(
            step=step,
            db=db,
            llm_client=llm_client,
            registry=registry,
            run_id=run_id,
            reformulation_hint=reformulation_hint,
        )
        return ACTION_RETRY_REFORMULATED, retry_result

    elif action == ACTION_SKIP_AND_FLAG:
        if retry_count >= 1:
            msg = (
                f"Step '{step.description}' failed again after retry ({classification}: {reasoning}) – "
                "skipping and flagging this gap rather than retrying."
            )
        else:
            msg = (
                f"Step '{step.description}' failed with a hard failure ({reasoning}) – "
                "skipping and flagging this gap rather than retrying."
            )
        logger.warning(msg)
        print(f"\n[Agent Self-Correction] {msg}")

        step.status = "skipped"
        step.result_ref = f"Skipped ({classification}): {reasoning}"
        db.commit()
        db.refresh(step)

        if run_id:
            event_emitter.emit(
                run_id=run_id,
                event_type=EVENT_REPLAN_TRIGGERED,
                payload={
                    "step_id": str(step.id),
                    "action": ACTION_SKIP_AND_FLAG,
                    "retry_count": retry_count,
                    "reasoning": reasoning,
                    "message": msg,
                },
            )
            event_emitter.emit(
                run_id=run_id,
                event_type=EVENT_STEP_COMPLETED,
                payload={
                    "step_id": str(step.id),
                    "status": step.status,
                    "result_ref": step.result_ref,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        return ACTION_SKIP_AND_FLAG, None

    return action, None
