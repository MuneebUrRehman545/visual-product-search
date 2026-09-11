"""
RAG module's database read/write functions.

Reuses the team's shared_database.py module (SHARED_DATABASE_URL,
get_shared_connection) instead of a separate connection file, so RAG
stays consistent with Vision and the Gateway on env variable naming
and connection handling.
"""

import json

from app.db.shared_database import (
    get_shared_connection,
    insert_module_event as _shared_insert_module_event,
    update_pipeline_run_status as _shared_update_pipeline_run_status,
)


# ----------------------------------------------------------------
# Reads
# ----------------------------------------------------------------

def fetch_extracted_data(extracted_data_id: str):
    """
    Fetch a single row from the shared extracted_data table by its id.
    Returns a dict or None if not found.
    """
    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM extracted_data WHERE id = %s;",
                (extracted_data_id,),
            )
            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            return dict(zip(columns, row)) if row else None


# ----------------------------------------------------------------
# Writes
# ----------------------------------------------------------------

def insert_rag_document(
    pipeline_run_id: str,
    extracted_data_id: str,
    summary: str,
    citations: list,
    grounded,
    groundedness_score,
    status: str,
):
    """
    Insert a row into rag_documents and return its generated id.

    rag_documents has no dedicated summary/citations/grounded/status
    columns — summary goes in `content`, everything else is packed
    into `metadata` as JSON.
    """
    metadata = {
        "citations": citations,
        "grounded": grounded,
        "groundedness_score": groundedness_score,
        "status": status,
    }

    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_documents (
                    pipeline_run_id, source_extracted_data_id, content, metadata
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id;
                """,
                (pipeline_run_id, extracted_data_id, summary, json.dumps(metadata)),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None


def insert_chat_history(pipeline_run_id: str, role: str, message: str):
    """Insert a row into chat_history (column is `content`, not `message`)."""
    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_history (pipeline_run_id, role, content)
                VALUES (%s, %s, %s);
                """,
                (pipeline_run_id, role, message),
            )


def insert_module_event(pipeline_run_id: str, event: str, payload: dict = None):
    """
    Thin wrapper around shared_database.insert_module_event so RAG's
    router.py can call it the same way it always has, while actually
    using the team's shared implementation (module='rag' fixed here).
    """
    return _shared_insert_module_event(
        pipeline_run_id=pipeline_run_id,
        event=event,
        payload=payload,
        module="rag",
    )


def update_pipeline_status(pipeline_run_id: str, status: str):
    """
    Thin wrapper around shared_database.update_pipeline_run_status,
    kept under RAG's own naming so router.py doesn't need to change.
    """
    return _shared_update_pipeline_run_status(pipeline_run_id, status)