from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.modules.rag.adapter import vision_to_context, build_vision_citation
from app.modules.rag.writes import (
    insert_rag_document,
    insert_chat_history,
    insert_module_event,
    fetch_extracted_data,
    update_pipeline_status,
)
from app.services.rag import ask_rag


router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


# ======================================================================
# ORIGINAL STANDALONE ENDPOINT — unchanged behaviour from the solo
# Lumis project. Kept working alongside the integration endpoint below,
# per team agreement: each module's standalone capability stays
# accessible through the unified app, not just the merged pipeline.
# ======================================================================

class ChatRequest(BaseModel):
    question: str
    history: Optional[list] = None


@router.post("/chat")
def chat(request: ChatRequest):
    result = ask_rag(request.question, history=request.history or [])
    return result


# ======================================================================
# INTEGRATION ENDPOINT — consumes Vision's extracted_data, runs RAG,
# writes to the shared rag_documents / chat_history / module_events
# tables, and updates pipeline_runs.status so the gateway can detect
# completion.
# ======================================================================

class RagProcessRequest(BaseModel):
    pipeline_run_id: str
    extracted_data_id: str
    question: Optional[str] = None


@router.post("/process")
def process(request: RagProcessRequest):

    insert_module_event(
        request.pipeline_run_id,
        "rag_started",
        {"extracted_data_id": request.extracted_data_id},
    )

    # ----------------------------------------------------
    # 1. Fetch Vision data from shared DB
    # ----------------------------------------------------

    vision_data = fetch_extracted_data(request.extracted_data_id)

    if vision_data is None:
        insert_module_event(request.pipeline_run_id, "rag_failed", {"reason": "not_found"})
        raise HTTPException(status_code=404, detail="extracted_data_id not found")

    # ----------------------------------------------------
    # 2. Convert Vision data to RAG context
    # ----------------------------------------------------

    context_text = vision_to_context(vision_data)

    if not context_text.strip():
        insert_module_event(request.pipeline_run_id, "rag_failed", {"reason": "insufficient_data"})

        rag_document_id = insert_rag_document(
            pipeline_run_id=request.pipeline_run_id,
            extracted_data_id=request.extracted_data_id,
            summary="",
            citations=[],
            grounded=False,
            groundedness_score=None,
            status="insufficient_data",
        )

        return {
            "pipeline_run_id": request.pipeline_run_id,
            "rag_document_id": rag_document_id,
            "summary": "",
            "citations": [],
            "grounded": False,
            "groundedness_score": None,
            "status": "insufficient_data",
        }

    # ----------------------------------------------------
    # 3. Run existing RAG pipeline
    # ----------------------------------------------------

    question = request.question or "Summarize this product record."

    if request.question:
        insert_chat_history(request.pipeline_run_id, "user", request.question)

    try:
        result = ask_rag(question, history=[])
    except Exception as error:
        insert_module_event(
            request.pipeline_run_id,
            "rag_failed",
            {"reason": "llm_unavailable", "error": str(error)},
        )

        rag_document_id = insert_rag_document(
            pipeline_run_id=request.pipeline_run_id,
            extracted_data_id=request.extracted_data_id,
            summary="",
            citations=[],
            grounded=False,
            groundedness_score=None,
            status="llm_unavailable",
        )

        return {
            "pipeline_run_id": request.pipeline_run_id,
            "rag_document_id": rag_document_id,
            "summary": "",
            "citations": [],
            "grounded": False,
            "groundedness_score": None,
            "status": "llm_unavailable",
        }

    # ----------------------------------------------------
    # 4. Build citations (document + catalog_item)
    # ----------------------------------------------------

    citations = [
        {
            "source_type": "document",
            "source": s.get("source"),
            "page_number": s.get("page_number"),
            "product_id": None,
            "image_url": None,
        }
        for s in result.get("sources", [])
    ]

    citations.append(build_vision_citation(vision_data))

    groundedness = result.get("groundedness")

    if groundedness is None:
        grounded = None
        groundedness_score = None
    else:
        grounded = not groundedness.get("flagged", False)
        groundedness_score = groundedness.get("groundedness_score")

    if request.question:
        insert_chat_history(request.pipeline_run_id, "bot", result.get("answer", ""))

    # ----------------------------------------------------
    # 5. Persist + respond
    # ----------------------------------------------------

    rag_document_id = insert_rag_document(
        pipeline_run_id=request.pipeline_run_id,
        extracted_data_id=request.extracted_data_id,
        summary=result.get("answer", ""),
        citations=citations,
        grounded=grounded,
        groundedness_score=groundedness_score,
        status="completed",
    )

    insert_module_event(
        request.pipeline_run_id,
        "rag_completed",
        {"rag_document_id": rag_document_id, "grounded": grounded},
    )

    update_pipeline_status(request.pipeline_run_id, "rag_complete")

    return {
        "pipeline_run_id": request.pipeline_run_id,
        "rag_document_id": rag_document_id,
        "summary": result.get("answer", ""),
        "citations": citations,
        "grounded": grounded,
        "groundedness_score": groundedness_score,
        "status": "completed",
    }