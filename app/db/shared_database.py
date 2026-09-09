"""Dedicated Shared PostgreSQL Database Service for Week 4 Multi-Agent Integration.

Manages cross-module pipeline persistence against Moeez's shared Supabase database:
- pipeline_runs verification
- assets registration
- extracted_data handoff (Vision -> RAG)
- module_events auditing

This service is strictly decoupled from the local Vision catalog database.
"""

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import uuid
from typing import Any, Dict, Generator, List, Optional

from dotenv import load_dotenv

# Load .env once from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

try:
    import psycopg2
    from psycopg2 import extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

logger = logging.getLogger("shared_pipeline.database")


def get_shared_database_url() -> Optional[str]:
    """Retrieve SHARED_DATABASE_URL from environment."""
    url = os.getenv("SHARED_DATABASE_URL")
    if url and url.strip():
        clean_url = url.strip()
        if clean_url.startswith("postgres://"):
            clean_url = "postgresql://" + clean_url[len("postgres://") :]
        return clean_url
    return None


def is_shared_db_configured() -> bool:
    """Check if SHARED_DATABASE_URL is set and points to PostgreSQL."""
    url = get_shared_database_url()
    return url is not None and url.startswith("postgresql://")


@contextmanager
def get_shared_connection() -> Generator[Any, None, None]:
    """Provide a transactional database connection for the shared Supabase PostgreSQL instance."""
    url = get_shared_database_url()
    if not url:
        raise RuntimeError("SHARED_DATABASE_URL is not configured in the environment.")
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is required for PostgreSQL. Please install psycopg2-binary.")

    conn = psycopg2.connect(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_pipeline_run_exists(pipeline_run_id: str) -> bool:
    """Verify that the supplied pipeline_run_id exists in the shared pipeline_runs table.

    Args:
        pipeline_run_id: UUID string of the pipeline run.

    Returns:
        bool: True if record exists, False otherwise.
    """
    try:
        val_uuid = uuid.UUID(pipeline_run_id)
    except (ValueError, TypeError):
        return False

    if not is_shared_db_configured():
        logger.warning("SHARED_DATABASE_URL not configured; skipping pipeline_run existence check.")
        return False

    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pipeline_runs WHERE id = %s;",
                (str(val_uuid),),
            )
            return cur.fetchone() is not None


def insert_asset(
    pipeline_run_id: str,
    filename: Optional[str] = None,
    mime_type: Optional[str] = "image/jpeg",
    storage_uri: Optional[str] = None,
    asset_type: str = "query_image",
) -> str:
    """Insert a query image asset into the shared assets table and return its UUID.

    Args:
        pipeline_run_id: Parent pipeline run UUID.
        filename: Original file name.
        mime_type: File MIME type (e.g. image/jpeg, image/png).
        storage_uri: Relative or absolute storage path / URI.
        asset_type: Classification string (default 'query_image').

    Returns:
        str: Generated asset UUID.
    """
    asset_uuid = str(uuid.uuid4())
    run_uuid = str(uuid.UUID(pipeline_run_id))
    fn = filename or "query_image.jpg"
    mt = mime_type or "image/jpeg"
    s_uri = storage_uri or f"assets/{fn}"

    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO assets (id, pipeline_run_id, asset_type, filename, mime_type, storage_uri, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                RETURNING id;
                """,
                (asset_uuid, run_uuid, asset_type, fn, mt, s_uri),
            )
            row = cur.fetchone()
            return str(row[0]) if row else asset_uuid


def insert_extracted_data(
    pipeline_run_id: str,
    content: Dict[str, Any],
    model: str,
    confidence: float,
    asset_id: Optional[str] = None,
    data_type: str = "visual_product_search_matches",
    module: str = "vision",
) -> str:
    """Insert structured visual search output into the shared extracted_data table.

    Args:
        pipeline_run_id: Parent pipeline run UUID.
        content: Structured dictionary containing primary_match and ranked matches.
        model: Embedding model name used (e.g. 'OpenCLIP_ViT_B_32', 'ResNet_50').
        confidence: Rank-1 cosine similarity score.
        asset_id: Optional UUID of parent asset record.
        data_type: Data type classification.
        module: Module identifier ('vision').

    Returns:
        str: Generated extracted_data UUID (handed off as extracted_data_id to RAG).
    """
    extracted_uuid = str(uuid.uuid4())
    run_uuid = str(uuid.UUID(pipeline_run_id))
    valid_asset_uuid = str(uuid.UUID(asset_id)) if asset_id else None

    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extracted_data (
                    id, pipeline_run_id, asset_id, module, data_type, content, model, confidence, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id;
                """,
                (
                    extracted_uuid,
                    run_uuid,
                    valid_asset_uuid,
                    module,
                    data_type,
                    extras.Json(content),
                    model,
                    float(confidence),
                ),
            )
            row = cur.fetchone()
            return str(row[0]) if row else extracted_uuid


def insert_module_event(
    pipeline_run_id: str,
    event: str,
    message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    module: str = "vision",
) -> Optional[str]:
    """Insert an execution lifecycle event into the shared module_events audit table.

    Args:
        pipeline_run_id: Parent pipeline run UUID.
        event: Lifecycle state ('started', 'completed', 'failed').
        message: Informational message.
        payload: Optional structured JSON metadata.
        module: Module identifier ('vision').

    Returns:
        Optional[str]: Event UUID if inserted successfully, None on error without raising.
    """
    try:
        event_uuid = str(uuid.uuid4())
        run_uuid = str(uuid.UUID(pipeline_run_id))
        msg = message or f"Module {module} {event}"
        p_json = extras.Json(payload) if payload is not None else None

        with get_shared_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO module_events (id, pipeline_run_id, module, event, message, payload, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id;
                    """,
                    (event_uuid, run_uuid, module, event, msg, p_json),
                )
                row = cur.fetchone()
                return str(row[0]) if row else event_uuid
    except Exception as e:
        logger.warning("Failed to record module_event '%s' for run '%s': %s", event, pipeline_run_id, e)
        return None


def update_pipeline_run_status(pipeline_run_id: str, status: str) -> bool:
    """Update the status of an existing pipeline_run record in the gateway/orchestration layer.

    Args:
        pipeline_run_id: Pipeline run UUID string.
        status: New status (e.g. 'vision_complete', 'completed', 'failed', 'vision_failed').

    Returns:
        bool: True if record was updated, False otherwise.
    """
    try:
        val_uuid = str(uuid.UUID(pipeline_run_id))
    except (ValueError, TypeError):
        return False

    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_runs
                SET status = %s, updated_at = NOW()
                WHERE id = %s;
                """,
                (status, val_uuid),
            )
            return cur.rowcount > 0


def get_pipeline_run(pipeline_run_id: str) -> Optional[Dict[str, Any]]:
    """Fetch pipeline_run metadata by UUID.

    Args:
        pipeline_run_id: UUID string of the pipeline run.

    Returns:
        Optional[Dict[str, Any]]: Run record dict or None if not found.
    """
    try:
        val_uuid = str(uuid.UUID(pipeline_run_id))
    except (ValueError, TypeError):
        return None

    with get_shared_connection() as conn:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, status, created_at, updated_at FROM pipeline_runs WHERE id = %s;",
                (val_uuid,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": str(row["id"]),
                    "status": row["status"],
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
                }
            return None


def get_extracted_data_by_run_id(pipeline_run_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the latest Vision module extracted_data record for a pipeline run.

    Filters specifically for module='vision' and data_type='visual_product_search_matches'
    so that downstream records from other modules (e.g., RAG) are not mistakenly returned.

    Args:
        pipeline_run_id: UUID string of the pipeline run.

    Returns:
        Optional[Dict[str, Any]]: Record dictionary with content JSONB and confidence.
    """
    try:
        val_uuid = str(uuid.UUID(pipeline_run_id))
    except (ValueError, TypeError):
        return None

    with get_shared_connection() as conn:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, pipeline_run_id, asset_id, module, data_type, content, model, confidence, created_at
                FROM extracted_data
                WHERE pipeline_run_id = %s
                  AND module = 'vision'
                  AND data_type = 'visual_product_search_matches'
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (val_uuid,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": str(row["id"]),
                    "pipeline_run_id": str(row["pipeline_run_id"]),
                    "asset_id": str(row["asset_id"]) if row.get("asset_id") else None,
                    "module": row["module"],
                    "data_type": row["data_type"],
                    "content": row["content"],
                    "model": row["model"],
                    "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                }
            return None


def get_assets_by_run_id(pipeline_run_id: str) -> List[Dict[str, Any]]:
    """Fetch all assets attached to a pipeline run.

    Args:
        pipeline_run_id: UUID string of the pipeline run.

    Returns:
        List[Dict[str, Any]]: List of asset records.
    """
    try:
        val_uuid = str(uuid.UUID(pipeline_run_id))
    except (ValueError, TypeError):
        return []

    with get_shared_connection() as conn:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, pipeline_run_id, asset_type, filename, mime_type, storage_uri, created_at
                FROM assets
                WHERE pipeline_run_id = %s
                ORDER BY created_at ASC;
                """,
                (val_uuid,),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "pipeline_run_id": str(r["pipeline_run_id"]),
                    "asset_type": r["asset_type"],
                    "filename": r["filename"],
                    "mime_type": r["mime_type"],
                    "storage_uri": r["storage_uri"],
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                }
                for r in rows
            ]


def get_module_events_by_run_id(pipeline_run_id: str) -> List[Dict[str, Any]]:
    """Fetch all module_events lifecycle audit logs for a pipeline run.

    Args:
        pipeline_run_id: UUID string of the pipeline run.

    Returns:
        List[Dict[str, Any]]: Chronological list of event records.
    """
    try:
        val_uuid = str(uuid.UUID(pipeline_run_id))
    except (ValueError, TypeError):
        return []

    with get_shared_connection() as conn:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, pipeline_run_id, module, event, message, payload, created_at
                FROM module_events
                WHERE pipeline_run_id = %s
                ORDER BY created_at ASC;
                """,
                (val_uuid,),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "pipeline_run_id": str(r["pipeline_run_id"]),
                    "module": r["module"],
                    "event": r["event"],
                    "message": r["message"],
                    "payload": r["payload"],
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                }
                for r in rows
            ]
