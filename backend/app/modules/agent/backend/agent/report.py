import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from sqlalchemy.orm import Session

import models
from agent.events import EVENT_REPORT_READY, event_emitter
from agent.llm_client import LLMClient
from database import get_db

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_report_system_prompt() -> str:
    prompt_file = PROMPTS_DIR / "report_prompt.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    return (
        "You are an expert AI research synthesizer and technical report writer.\n"
        "Your task is to write a comprehensive, professional, structured research report in Markdown format "
        "based ONLY on the verified findings gathered during the autonomous research run.\n\n"
        "Strict Guidelines:\n"
        "1. Grounding: Only use the verified findings provided below. Do not add facts from your own general knowledge.\n"
        "2. Honest Limitations: If a planned finding was skipped, mention it honestly in a Limitations section. "
        "Do not invent or assume data that was not gathered.\n"
        "3. Structure: Structure the report with: a title (# Title), a short intro restating the objective "
        "(## Introduction / Objective), 2-4 topic sections based on the findings, a key findings summary "
        "(## Key Findings Summary), and a Limitations/Gaps section (## Limitations & Gaps) - OMIT this section "
        "only if literally nothing was skipped."
    )


def _format_step_finding(step: models.Step) -> str:
    """Formats findings from a single completed step and its tool call outputs."""
    parts = [f"### Step: {step.description} (Tool: {step.intended_tool})"]
    if step.tool_calls:
        for idx, tc in enumerate(step.tool_calls, start=1):
            status_str = "Success" if tc.success else "Failed"
            output_str = json.dumps(tc.output_data) if isinstance(tc.output_data, (dict, list)) else str(tc.output_data)
            parts.append(
                f"- Tool Call {idx} [{tc.tool_name}] ({status_str}):\n"
                f"  Arguments: {json.dumps(tc.input_args)}\n"
                f"  Output: {output_str}"
            )
            if tc.error_message:
                parts.append(f"  Error: {tc.error_message}")
    elif step.observation and step.observation.reasoning:
        parts.append(f"- Observation: {step.observation.reasoning}")
    elif step.result_ref:
        parts.append(f"- Result: {step.result_ref}")
    else:
        parts.append("- Step completed successfully.")

    return "\n".join(parts)


def _format_fallback_report(
    goal_text: str,
    completed_steps: list[models.Step],
    skipped_steps: list[models.Step],
    stop_reason: Optional[str] = None,
) -> str:
    """Generates a structured fallback Markdown report matching the strict template requirements."""
    sections = [f"# Research Report: {goal_text}\n"]
    sections.append("## Introduction & Objective")
    sections.append(f"This report presents research findings synthesized for the objective: *{goal_text}*.\n")

    sections.append("## Key Findings Summary")
    if completed_steps:
        summaries = []
        for s in completed_steps:
            if s.observation and s.observation.reasoning:
                summaries.append(f"- **{s.description}**: {s.observation.reasoning}")
            elif s.result_ref:
                summaries.append(f"- **{s.description}**: {s.result_ref}")
            else:
                summaries.append(f"- **{s.description}**: Completed successfully.")
        sections.append("\n".join(summaries) + "\n")
    else:
        sections.append("No findings were successfully gathered during execution.\n")

    if completed_steps:
        sections.append("## Detailed Research Findings")
        for step in completed_steps:
            sections.append(f"### {step.description}")
            if step.tool_calls:
                for tc in step.tool_calls:
                    if tc.output_data:
                        sections.append(f"```json\n{json.dumps(tc.output_data, indent=2)}\n```")
                    elif tc.error_message:
                        sections.append(f"*Tool {tc.tool_name} note*: {tc.error_message}")
            elif step.observation:
                sections.append(step.observation.reasoning)
            sections.append("")

    # Only include Limitations section if there are actually skipped steps
    if skipped_steps:
        sections.append("## Limitations & Gaps")
        sections.append("The following planned steps could not be completed and were skipped during execution:")
        for s in skipped_steps:
            reason = "No reason recorded"
            if s.observation and s.observation.reasoning:
                reason = f"{s.observation.classification.upper()}: {s.observation.reasoning}"
            elif s.result_ref:
                reason = s.result_ref
            sections.append(f"- **{s.description}**: {reason}")
        sections.append("")

    if stop_reason:
        sections.append(f"*(Run note: {stop_reason})*")

    return "\n\n".join(sections).strip()


def generate_report(
    run_id: Union[str, uuid.UUID],
    db: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    stop_reason: Optional[str] = None,
) -> models.Report:
    """Gathers all findings and skipped steps from the run, invokes the LLM with the
    dedicated report-writing prompt, saves the resulting Markdown to the reports table,
    and returns the Report ORM instance.

    If report generation fails, raises an exception so orchestrator can mark the run failed.
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
        target_run_id = uuid.UUID(str(run_id)) if isinstance(run_id, str) else run_id
        run = db.query(models.Run).filter(models.Run.id == target_run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found in database.")

        # a. Gathers ALL findings from this run:
        # Every step marked "complete" / "completed" with tool_call output_data
        completed_steps = (
            db.query(models.Step)
            .join(models.Plan, models.Step.plan_id == models.Plan.id)
            .filter(
                models.Plan.run_id == target_run_id,
                models.Step.status.in_(["complete", "completed"]),
            )
            .order_by(models.Step.created_at.asc())
            .all()
        )

        # Every step marked "skipped" with reason from observation
        skipped_steps = (
            db.query(models.Step)
            .join(models.Plan, models.Step.plan_id == models.Plan.id)
            .filter(
                models.Plan.run_id == target_run_id,
                models.Step.status == "skipped",
            )
            .order_by(models.Step.created_at.asc())
            .all()
        )

        findings_formatted = "\n\n".join([_format_step_finding(s) for s in completed_steps])
        
        skipped_info_lines = []
        if skipped_steps:
            for s in skipped_steps:
                reason = "Skipped"
                if s.observation and s.observation.reasoning:
                    reason = f"[{s.observation.classification.upper()}] {s.observation.reasoning}"
                elif s.result_ref:
                    reason = s.result_ref
                skipped_info_lines.append(f"- Step: '{s.description}' (Intended Tool: {s.intended_tool}) -> Reason: {reason}")
            skipped_formatted = "\n".join(skipped_info_lines)
        else:
            skipped_formatted = "None. All planned steps completed successfully. (OMIT the Limitations/Gaps section entirely)."

        # b. Calls the LLM with dedicated report-writing prompt
        system_prompt = _load_report_system_prompt()
        user_message = f"""Research Objective: {run.goal_text}

=== VERIFIED FINDINGS FROM COMPLETED STEPS ===
{findings_formatted if findings_formatted.strip() else 'No completed step findings recorded.'}

=== SKIPPED STEPS AND LIMITATIONS ===
{skipped_formatted}

=== EXECUTION NOTE ===
{stop_reason or 'Research plan completed.'}
"""

        if llm_client is None:
            try:
                llm_client = LLMClient()
            except Exception:
                llm_client = None

        content_markdown = None
        if llm_client is not None and getattr(llm_client, "api_key", None):
            try:
                report_response = llm_client.generate(
                    system_prompt=system_prompt,
                    user_message=user_message,
                )
                if report_response and report_response.strip():
                    content_markdown = report_response.strip()
            except Exception as llm_err:
                logger.warning(f"LLM report generation call failed: {llm_err}. Using fallback formatter.")

        if not content_markdown:
            content_markdown = _format_fallback_report(
                goal_text=run.goal_text,
                completed_steps=completed_steps,
                skipped_steps=skipped_steps,
                stop_reason=stop_reason,
            )

        # c. Saves the resulting Markdown report to the reports table
        existing_report = db.query(models.Report).filter(models.Report.run_id == target_run_id).first()
        if existing_report:
            existing_report.content_markdown = content_markdown
            report_obj = existing_report
        else:
            report_obj = models.Report(
                run_id=target_run_id,
                content_markdown=content_markdown,
                created_at=datetime.now(timezone.utc),
            )
            db.add(report_obj)

        db.commit()
        db.refresh(report_obj)
        logger.info(f"Report for run {target_run_id} successfully generated and saved.")

        event_emitter.emit(
            run_id=target_run_id,
            event_type=EVENT_REPORT_READY,
            payload={
                "report_id": str(report_obj.id),
                "run_id": str(report_obj.run_id),
                "content_markdown": report_obj.content_markdown,
                "created_at": report_obj.created_at.isoformat() if report_obj.created_at else None,
            },
        )

        return report_obj

    finally:
        if own_db and db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass
