import logging
import uuid
from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

import models
from database import get_db

logger = logging.getLogger(__name__)


def _summarize_tool_call(
    tool_name: str,
    input_args: dict,
    output_data: Any,
    success: bool,
    error_message: Optional[str],
) -> str:
    """Produces a 1-2 sentence summary of a single tool call execution."""
    if not success:
        return f"Tool '{tool_name}' failed: {error_message or 'Unknown error'}."

    if tool_name == "web_search":
        if isinstance(output_data, dict):
            results = output_data.get("results")
            if isinstance(results, list) and results:
                snippets = []
                for item in results[:2]:
                    if isinstance(item, dict):
                        snip = item.get("snippet") or item.get("content") or item.get("title") or ""
                        if snip:
                            snippets.append(snip)
                    elif isinstance(item, str):
                        snippets.append(item)
                if snippets:
                    combined = " ".join(snippets)
                    if len(combined) > 250:
                        combined = combined[:247] + "..."
                    return f"Web search found: {combined}"
            summary_val = output_data.get("summary") or output_data.get("content")
            if summary_val:
                text = str(summary_val)
                if len(text) > 250:
                    text = text[:247] + "..."
                return f"Web search summary: {text}"
        return f"Web search completed successfully: {str(output_data)[:200]}."

    elif tool_name in ("calculator", "calc"):
        if isinstance(output_data, dict) and "result" in output_data:
            expr = input_args.get("expression") or input_args.get("expr") or ""
            res = output_data["result"]
            if expr:
                return f"Calculated {expr} = {res}."
            return f"Calculated result: {res}."
        return f"Calculator returned: {str(output_data)[:200]}."

    elif tool_name in ("file_write", "write_file", "file_read_write"):
        filename = input_args.get("filename") or input_args.get("filepath") or "file"
        if isinstance(output_data, dict) and "bytes_written" in output_data:
            bytes_w = output_data["bytes_written"]
            return f"Saved output to {filename} ({bytes_w} bytes)."
        return f"Wrote output to {filename}."

    elif tool_name in ("file_read", "read_file"):
        filename = input_args.get("filename") or input_args.get("filepath") or "file"
        if isinstance(output_data, dict) and "content" in output_data:
            content = str(output_data["content"])
            if len(content) > 250:
                content = content[:247] + "..."
            return f"Read {filename}: {content}"
        return f"Read file {filename} successfully."

    elif tool_name == "echo":
        if isinstance(output_data, dict) and "echoed" in output_data:
            return f"Echoed: {output_data['echoed']}"

    # Generic fallback
    if isinstance(output_data, dict):
        if "result" in output_data:
            return f"Finding: {output_data['result']}"
        elif "summary" in output_data:
            return f"Finding: {output_data['summary']}"

    output_str = str(output_data) if output_data is not None else ""
    if len(output_str) > 200:
        output_str = output_str[:197] + "..."
    return f"Tool '{tool_name}' result: {output_str}"


def _summarize_step(step: models.Step) -> str:
    """Summarizes a completed step's findings in 1-2 sentences."""
    parts = []
    if step.tool_calls:
        for tc in step.tool_calls:
            parts.append(_summarize_tool_call(tc.tool_name, tc.input_args, tc.output_data, tc.success, tc.error_message))
    elif step.observation and step.observation.reasoning:
        parts.append(step.observation.reasoning)
    elif step.result_ref:
        parts.append(f"Result reference: {step.result_ref}")
    else:
        parts.append("Step completed successfully.")

    finding = " ".join(parts)
    return f"Step '{step.description}': {finding}"


def build_context_summary(
    run_id: Union[str, uuid.UUID],
    db: Optional[Session] = None,
) -> str:
    """Queries all COMPLETED steps and their tool call results for run_id so far,
    and produces a short, condensed text summary (1-2 sentences per step).

    Excludes steps that haven't completed yet.
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
            target_run_id = uuid.UUID(run_id)
        else:
            target_run_id = run_id

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

        if not completed_steps:
            return ""

        summaries = [_summarize_step(s) for s in completed_steps]
        return "\n".join(summaries)

    finally:
        if own_db and db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass
