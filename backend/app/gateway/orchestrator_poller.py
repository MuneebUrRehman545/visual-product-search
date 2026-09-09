"""Polling orchestration for the Vision -> RAG -> Agent pipeline handoffs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx

from app.db.shared_database import (
    get_extracted_data_by_run_id,
    get_shared_connection,
)
from backend.app.modules.agent.adapter import run_agent

logger = logging.getLogger(__name__)

# RAG remains an HTTP contract even when it is served from the same process.
# Allow deployments to override the loopback URL without changing orchestration code.
RAG_PROCESS_URL = os.getenv(
    "RAG_PROCESS_URL",
    "http://127.0.0.1:8000/api/v1/rag/process",
)
RAG_REQUEST_TIMEOUT_SECONDS = 30.0


def _list_run_ids_with_status(status: str) -> list[str]:
    """Return pipeline runs that are ready for a downstream handoff."""
    with get_shared_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM pipeline_runs WHERE status = %s;",
                (status,),
            )
            return [str(row[0]) for row in cursor.fetchall()]


def _insert_module_event(
    cursor: Any,
    *,
    pipeline_run_id: str,
    module: str,
    event: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    """Record the state transition in the shared module event audit log."""
    cursor.execute(
        """
        INSERT INTO module_events (
            id, pipeline_run_id, module, event, message, payload, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW());
        """,
        (
            str(uuid.uuid4()),
            pipeline_run_id,
            module,
            event,
            message,
            json.dumps(payload),
        ),
    )


def _claim_run(
    *,
    pipeline_run_id: str,
    expected_status: str,
    claimed_status: str,
    module: str,
) -> bool:
    """Atomically claim a run only while it is in the expected state."""
    logger.info(
        "Poller claim attempted: run=%s %s -> %s",
        pipeline_run_id,
        expected_status,
        claimed_status,
    )

    with get_shared_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs
                SET status = %s, updated_at = NOW()
                WHERE id = %s AND status = %s;
                """,
                (claimed_status, pipeline_run_id, expected_status),
            )

            if cursor.rowcount != 1:
                return False

            _insert_module_event(
                cursor,
                pipeline_run_id=pipeline_run_id,
                module=module,
                event=claimed_status,
                message=f"Gateway poller claimed run for {module} processing.",
                payload={
                    "triggered_by": "gateway_poller",
                    "previous_status": expected_status,
                },
            )
            return True


def _mark_failed(
    *,
    pipeline_run_id: str,
    expected_status: str,
    failed_status: str,
    module: str,
    error: Exception,
) -> bool:
    """Move a claimed run to its failure state and persist an audit event."""
    error_message = str(error)

    with get_shared_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs
                SET status = %s, updated_at = NOW()
                WHERE id = %s AND status = %s;
                """,
                (failed_status, pipeline_run_id, expected_status),
            )

            if cursor.rowcount != 1:
                return False

            _insert_module_event(
                cursor,
                pipeline_run_id=pipeline_run_id,
                module=module,
                event=failed_status,
                message=f"{module.upper()} trigger failed: {error_message}",
                payload={
                    "triggered_by": "gateway_poller",
                    "error": error_message,
                },
            )
            return True


async def _trigger_rag(pipeline_run_id: str) -> None:
    """Fetch Vision output and synchronously invoke RAG's HTTP contract."""
    extracted_data = await asyncio.to_thread(
        get_extracted_data_by_run_id,
        pipeline_run_id,
    )
    if not extracted_data:
        raise RuntimeError("No Vision extracted_data record exists for this pipeline run.")

    extracted_data_id = extracted_data["id"]
    payload = {
        "pipeline_run_id": pipeline_run_id,
        "extracted_data_id": extracted_data_id,
        "question": None,
    }

    logger.info(
        "Calling RAG: run=%s extracted_data_id=%s url=%s",
        pipeline_run_id,
        extracted_data_id,
        RAG_PROCESS_URL,
    )
    async with httpx.AsyncClient(timeout=RAG_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(RAG_PROCESS_URL, json=payload)
        response.raise_for_status()

    logger.info(
        "RAG call succeeded: run=%s status_code=%s",
        pipeline_run_id,
        response.status_code,
    )


async def _trigger_agent(pipeline_run_id: str) -> None:
    """Invoke the mounted Agent implementation directly in-process."""
    logger.info("Calling Agent: run=%s", pipeline_run_id)
    response = await run_agent(pipeline_run_id)
    logger.info(
        "Agent call succeeded: run=%s agent_run_id=%s status=%s",
        pipeline_run_id,
        response.agent_run_id,
        response.status,
    )


async def poll_and_trigger() -> None:
    """Claim completed upstream stages and start their downstream modules."""
    vision_complete_runs = await asyncio.to_thread(
        _list_run_ids_with_status,
        "vision_complete",
    )
    if vision_complete_runs:
        logger.info("Poller found %s Vision-complete run(s).", len(vision_complete_runs))

    for pipeline_run_id in vision_complete_runs:
        claimed = await asyncio.to_thread(
            _claim_run,
            pipeline_run_id=pipeline_run_id,
            expected_status="vision_complete",
            claimed_status="rag_processing",
            module="rag",
        )
        if not claimed:
            logger.info(
                "RAG claim not acquired: run=%s; another worker already handled it.",
                pipeline_run_id,
            )
            continue

        logger.info("RAG claim succeeded: run=%s", pipeline_run_id)
        try:
            await _trigger_rag(pipeline_run_id)
        except Exception as exc:
            logger.exception("RAG trigger failed: run=%s", pipeline_run_id)
            marked_failed = await asyncio.to_thread(
                _mark_failed,
                pipeline_run_id=pipeline_run_id,
                expected_status="rag_processing",
                failed_status="rag_failed",
                module="rag",
                error=exc,
            )
            logger.info(
                "RAG failure status recorded=%s: run=%s",
                marked_failed,
                pipeline_run_id,
            )

    rag_complete_runs = await asyncio.to_thread(
        _list_run_ids_with_status,
        "rag_complete",
    )
    if rag_complete_runs:
        logger.info("Poller found %s RAG-complete run(s).", len(rag_complete_runs))

    for pipeline_run_id in rag_complete_runs:
        claimed = await asyncio.to_thread(
            _claim_run,
            pipeline_run_id=pipeline_run_id,
            expected_status="rag_complete",
            claimed_status="agent_processing",
            module="agent",
        )
        if not claimed:
            logger.info(
                "Agent claim not acquired: run=%s; another worker already handled it.",
                pipeline_run_id,
            )
            continue

        logger.info("Agent claim succeeded: run=%s", pipeline_run_id)
        try:
            await _trigger_agent(pipeline_run_id)
        except Exception as exc:
            logger.exception("Agent trigger failed: run=%s", pipeline_run_id)
            marked_failed = await asyncio.to_thread(
                _mark_failed,
                pipeline_run_id=pipeline_run_id,
                expected_status="agent_processing",
                failed_status="agent_failed",
                module="agent",
                error=exc,
            )
            logger.info(
                "Agent failure status recorded=%s: run=%s",
                marked_failed,
                pipeline_run_id,
            )
