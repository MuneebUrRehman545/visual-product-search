import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models
from agent.context import build_context_summary
from agent.evaluator import (
    ObservationResult,
    check_stopping_condition,
    classify_observation,
)
from agent.events import EVENT_RUN_COMPLETED, EVENT_RUN_FAILED, event_emitter
from agent.execution import execute_step
from agent.llm_client import LLMClient
from agent.planning import create_plan
from agent.report import generate_report
from agent.self_correction import (
    ACTION_CONTINUE,
    ACTION_RETRY_REFORMULATED,
    ACTION_RETRY_SAME,
    ACTION_SKIP_AND_FLAG,
    apply_self_correction,
    decide_correction,
)
from agent.tools import default_registry
from agent.tools.registry import ToolRegistry
from database import get_db

logger = logging.getLogger(__name__)


def synthesize_report(
    run: models.Run,
    db: Session,
    llm_client: Optional[LLMClient] = None,
    stop_reason: Optional[str] = None,
) -> str:
    """Synthesizes all findings into a comprehensive Markdown report using generate_report."""
    report_obj = generate_report(
        run_id=run.id,
        db=db,
        llm_client=llm_client,
        stop_reason=stop_reason,
    )
    return report_obj.content_markdown


def run_agent(
    run_id: str | uuid.UUID,
    db: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    registry: Optional[ToolRegistry] = None,
) -> Optional[models.Run]:
    """Orchestrates an agent run through the complete autonomous research cycle:
    1. Fetches the run from DB and updates status to 'in_progress'.
    2. Generates (or retrieves) a structured multi-step plan.
    3. Main Loop:
       - Executes each step via tool selection and dispatch.
       - Evaluates and classifies observations (success, insufficient, transient_failure, hard_failure).
       - Applies self-correction logic (continue, retry_same, retry_reformulated, skip_and_flag) with retry capping.
       - Evaluates stopping conditions (LLM goal sufficiency + Hard safety cap: max 15 steps or 10 minutes).
    4. Synthesizes a final Markdown report.
    5. Updates run status to 'complete'.
    """
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
        if isinstance(run_id, str):
            run_id = uuid.UUID(run_id)

        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        if not run:
            logger.error(f"Run {run_id} not found in database.")
            return None

        # Update status to in_progress
        run.status = "in_progress"
        db.commit()
        db.refresh(run)

        # Restate the objective
        logger.info(f"Restating objective for Run {run.id}: {run.goal_text}")
        print(f"\n[Agent] Objective for Run {run.id}: {run.goal_text}")

        if llm_client is None:
            try:
                llm_client = LLMClient()
            except Exception:
                llm_client = None

        if registry is None:
            registry = default_registry

        start_time = time.time()
        total_steps_executed = 0
        step_retries: dict[uuid.UUID, int] = {}
        stop_reason: Optional[str] = None

        try:
            # 1. Plan Phase
            current_plan = (
                db.query(models.Plan)
                .filter(models.Plan.run_id == run.id, models.Plan.is_current == True)
                .first()
            )
            if not current_plan or not current_plan.steps:
                current_plan = create_plan(
                    objective_text=run.goal_text,
                    run_id=run.id,
                    db=db,
                    llm_client=llm_client,
                )

            logger.info(f"Active plan {current_plan.id} has {len(current_plan.steps)} steps for run {run.id}:")
            print(f"\n[Agent] Active Plan ({len(current_plan.steps)} steps):")
            for idx, step in enumerate(current_plan.steps, start=1):
                logger.info(f"  Step {idx}: {step.description} [Tool: {step.intended_tool}]")
                print(f"  {idx}. {step.description} [Tool: {step.intended_tool}]")

            # 2. Main Execution Cycle
            while True:
                # Fetch next pending step in plan order
                step = (
                    db.query(models.Step)
                    .filter(models.Step.plan_id == current_plan.id, models.Step.status == "pending")
                    .order_by(models.Step.created_at.asc())
                    .first()
                )

                if not step:
                    logger.info("No more pending steps remaining in plan.")
                    break

                # Pre-execution stopping condition check (including hard cap)
                should_stop, stop_reason = check_stopping_condition(
                    run_id=run.id,
                    db=db,
                    llm_client=llm_client,
                    step_count=total_steps_executed,
                    start_time=start_time,
                )
                if should_stop:
                    logger.info(f"Stopping condition met before step {step.id}: {stop_reason}")
                    print(f"\n[Agent] Stopping condition met: {stop_reason}")
                    break

                # Execute Step
                logger.info(f"Executing step {step.id}: '{step.description}' [Tool: {step.intended_tool}]")
                print(f"\n--- [Agent] Executing Step: '{step.description}' [Tool: {step.intended_tool}] ---")
                tool_result = execute_step(
                    step=step,
                    db=db,
                    llm_client=llm_client,
                    registry=registry,
                    run_id=run.id,
                )
                total_steps_executed += 1
                db.refresh(step)

                # Self-Correction Loop for this step
                while True:
                    obs = (
                        db.query(models.Observation)
                        .filter(models.Observation.step_id == step.id)
                        .first()
                    )
                    if not obs:
                        obs = classify_observation(
                            step=step,
                            tool_result=tool_result,
                            llm_client=llm_client,
                            db=db,
                            objective_text=run.goal_text,
                        )

                    current_retries = step_retries.get(step.id, 0)
                    action = decide_correction(obs, step=step, retry_count=current_retries)

                    if action == ACTION_CONTINUE:
                        logger.info(f"Step '{step.description}' classified as success – continuing.")
                        break

                    if action in (ACTION_RETRY_SAME, ACTION_RETRY_REFORMULATED):
                        step_retries[step.id] = current_retries + 1
                        total_steps_executed += 1
                        _, tool_result = apply_self_correction(
                            step=step,
                            observation=obs,
                            retry_count=current_retries,
                            db=db,
                            llm_client=llm_client,
                            registry=registry,
                            run_id=run.id,
                        )
                        db.refresh(step)
                        # Loop continues to evaluate the retry's outcome
                    elif action == ACTION_SKIP_AND_FLAG:
                        apply_self_correction(
                            step=step,
                            observation=obs,
                            retry_count=current_retries,
                            db=db,
                            llm_client=llm_client,
                            registry=registry,
                            run_id=run.id,
                        )
                        db.refresh(step)
                        break

                # Post-step stopping condition check
                should_stop, stop_reason = check_stopping_condition(
                    run_id=run.id,
                    db=db,
                    llm_client=llm_client,
                    step_count=total_steps_executed,
                    start_time=start_time,
                )
                if should_stop:
                    logger.info(f"Stopping condition met after step {step.id}: {stop_reason}")
                    print(f"\n[Agent] Stopping condition met: {stop_reason}")
                    break

            # 3. Report Generation Phase (Phase 14)
            logger.info(f"Generating final research report for Run {run.id}...")
            print("\n[Agent] Generating final research report...")
            generate_report(
                run_id=run.id,
                db=db,
                llm_client=llm_client,
                stop_reason=stop_reason,
            )

            # Ensure run status only becomes complete AFTER report is successfully generated and saved
            run.status = "complete"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(run)

            event_emitter.emit(
                run_id=run.id,
                event_type=EVENT_RUN_COMPLETED,
                payload={
                    "run_id": str(run.id),
                    "status": "complete",
                    "completed_at": run.completed_at.isoformat() if run.completed_at else datetime.now(timezone.utc).isoformat(),
                    "total_steps_executed": total_steps_executed,
                },
            )

            return run

        except Exception as err:
            logger.error(f"Agent execution failed for run {run_id}: {err}")
            error_message = str(err)
            run_uuid = uuid.UUID(str(run_id)) if isinstance(run_id, str) else run_id
            try:
                db.rollback()
                existing_report = db.query(models.Report).filter(models.Report.run_id == run_uuid).first()
                if existing_report:
                    existing_report.content_markdown = f"Run encountered fatal error: {error_message}"
                else:
                    error_report = models.Report(
                        run_id=run_uuid,
                        content_markdown=f"Run encountered fatal error: {error_message}",
                    )
                    db.add(error_report)

                target_run = db.query(models.Run).filter(models.Run.id == run_uuid).first()
                if target_run:
                    target_run.status = "failed"
                    target_run.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception as db_rec_err:
                logger.error(f"Failed to record failure state in DB: {db_rec_err}")

            event_emitter.emit(
                run_id=run_uuid,
                event_type=EVENT_RUN_FAILED,
                payload={
                    "run_id": str(run_uuid),
                    "status": "failed",
                    "error_message": error_message,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            return run

    finally:
        if own_db and db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass
