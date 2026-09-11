from typing import List, Dict, Optional
from collections import defaultdict
import re
from app.db.qdrant_connection import client, COLLECTION_NAME
from app.ingestion.embedder import get_model
from app.retrieval.hybrid_search import HybridRetriever
from app.llm.gemini import rewrite_question, generate_answer
from app.services.hallucination_check import check_groundedness


# ==========================================================
# Configuration
# ==========================================================

VECTOR_LIMIT = 30
HYBRID_TOP_K = 8
FINAL_TOP_K = 6

MIN_VECTOR_SIMILARITY = 0.28
MIN_VECTOR_SIMILARITY_NO_KEYWORD = 0.40


# ==========================================================
# Greeting / Acknowledgement Detection
#
# Casual messages ("hi", "thanks") aren't document questions,
# so running them through vector search/the no-match gate
# incorrectly returns "I couldn't find that information."
# Catch these early and respond conversationally instead.
# ==========================================================

GREETING_PATTERNS = {
    "hi", "hii", "hiii", "hiya", "hello", "helo", "hey", "heyy",
    "hola", "yo", "sup", "whats up", "wassup",
    "good morning", "good afternoon", "good evening", "good day",
    "greetings", "howdy",
    "salaam", "salam", "assalam o alaikum", "asalam o alaikum",
    "assalamualaikum", "aoa", "as salam",
}

ACKNOWLEDGEMENT_PATTERNS = {
    "thanks", "thank you", "thanks!", "thank you!", "ty",
    "thankyou", "thnx", "thx",
    "ok", "okay", "cool", "nice", "great", "awesome", "perfect",
    "got it", "understood", "alright",
}


def _is_greeting(query: str) -> bool:

    normalized = re.sub(r"[^a-z\s]", "", query.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized in GREETING_PATTERNS


def _is_acknowledgement(query: str) -> bool:

    normalized = re.sub(r"[^a-z\s]", "", query.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized in ACKNOWLEDGEMENT_PATTERNS


def _greeting_response() -> str:

    return (
        "Hi there! ≡ƒæï I'm ready to help you explore your documents. "
        "Upload a file (PDF, TXT, Markdown, or Word) or ask me a "
        "question about what's already in the knowledge base."
    )


def _acknowledgement_response() -> str:

    return "You're welcome! ≡ƒÿè Let me know if you have any other questions."


# ==========================================================
# Text Helpers
# ==========================================================

def _normalize_source(source: object) -> str:
    if not source:
        return ""

    source = str(source).strip().replace("\\", "/")
    source = source.split("/")[-1]

    while source.lower().endswith(".pdf.pdf"):
        source = source[:-4]

    return source.lower()


def _source_display_name(source: object) -> str:
    if not source:
        return ""

    source = str(source).strip().replace("\\", "/")
    source = source.split("/")[-1]

    while source.lower().endswith(".pdf.pdf"):
        source = source[:-4]

    return source


def _clean_text(text: object) -> str:
    if text is None:
        return ""

    return str(text).strip()


# ==========================================================
# Query Helpers
# ==========================================================

def _extract_query_keywords(query: str) -> List[str]:
    if not query:
        return []

    words = re.findall(
        r"[A-Za-z0-9]+",
        query.lower()
    )

    stop_words = {
        "the", "a", "an",
        "is", "are", "was", "were",
        "who", "what", "where",
        "when", "why", "how",
        "do", "does", "did",
        "about", "information",
        "mentioned", "tell",
        "me", "please",
        "can", "you", "give",
        "for", "of", "in",
        "on", "to", "and",
        "or", "this", "that",
        "him", "her", "his",
        "their", "they",
        "it", "he", "she",
        "with", "from",
        "document", "file",
    }

    return [
        word
        for word in words
        if word not in stop_words
        and len(word) >= 2
    ]


# ==========================================================
# Keyword Match Check
# ==========================================================

def _has_keyword_match(
    query: str,
    vector_results: List[Dict],
) -> bool:
    keywords = _extract_query_keywords(query)

    if not keywords:
        return False

    for document in vector_results:

        source = _normalize_source(
            document.get("source")
        )

        if not source:
            continue

        filename = source.rsplit(".", 1)[0]

        filename_words = set(
            re.findall(r"[a-z0-9]+", filename)
        )

        if any(keyword in filename_words for keyword in keywords):
            return True

    return False


# ==========================================================
# Qdrant Vector Search
# ==========================================================

def _vector_search(
    query: str,
    limit: int = VECTOR_LIMIT,
) -> List[Dict]:

    if not query or not query.strip():
        return []

    print("Creating query embedding...")

    query_vector = get_model().encode(
        query,
        normalize_embeddings=True,
    ).tolist()

    print("Searching Qdrant...")

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=limit,
        with_payload=True,
    )

    documents = []

    for point in result.points:

        payload = point.payload or {}

        text = _clean_text(
            payload.get("text", "")
        )

        source = _source_display_name(
            payload.get(
                "source",
                "Unknown"
            )
        )

        if not text:
            continue

        documents.append({
            "text": text,
            "source": source,
            "page_number": payload.get(
                "page_number"
            ),
            "chunk_id": payload.get(
                "chunk_id",
                point.id
            ),
            "similarity": float(
                getattr(
                    point,
                    "score",
                    0.0
                )
            ),
        })

    return documents


# ==========================================================
# Load All Documents
# ==========================================================

def _load_all_documents() -> List[Dict]:

    documents = []

    offset = None

    while True:

        points, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            offset=offset,
            with_payload=True,
        )

        if not points:
            break

        for point in points:

            payload = point.payload or {}

            text = _clean_text(
                payload.get("text", "")
            )

            source = _source_display_name(
                payload.get(
                    "source",
                    "Unknown"
                )
            )

            if not text:
                continue

            documents.append({
                "text": text,
                "source": source,
                "page_number": payload.get(
                    "page_number"
                ),
                "chunk_id": payload.get(
                    "chunk_id",
                    point.id
                ),
            })

        offset = next_offset

        if offset is None:
            break

    return documents


# ==========================================================
# Select Target Source
# ==========================================================

def _select_target_source(
    query: str,
    vector_results: List[Dict],
) -> Optional[str]:

    if not vector_results:
        return None

    keywords = _extract_query_keywords(
        query
    )

    source_scores = defaultdict(float)

    for document in vector_results:

        source = _normalize_source(
            document.get("source")
        )

        if not source:
            continue

        filename = source.rsplit(
            ".",
            1
        )[0]

        filename_words = set(
            re.findall(
                r"[a-z0-9]+",
                filename
            )
        )

        matches = sum(
            1
            for keyword in keywords
            if keyword in filename_words
        )

        if matches:

            source_scores[source] += (
                matches * 20.0
            )

    for rank, document in enumerate(
        vector_results,
        start=1
    ):

        source = _normalize_source(
            document.get("source")
        )

        if not source:
            continue

        score = float(
            document.get(
                "similarity",
                0.0
            )
        )

        source_scores[source] += (
            score * (1.0 / rank)
        )

    if not source_scores:
        return None

    return max(
        source_scores,
        key=source_scores.get
    )


# ==========================================================
# Filter By Source
# ==========================================================

def _filter_by_source(
    documents: List[Dict],
    selected_source: str,
) -> List[Dict]:

    target = _normalize_source(
        selected_source
    )

    return [
        document
        for document in documents
        if _normalize_source(
            document.get("source")
        ) == target
    ]


# ==========================================================
# Deduplicate Chunks
# ==========================================================

def _deduplicate_chunks(
    chunks: List[Dict],
) -> List[Dict]:

    seen = set()
    result = []

    for chunk in chunks:

        source = _normalize_source(
            chunk.get("source")
        )

        page = str(
            chunk.get(
                "page_number",
                ""
            )
        )

        chunk_id = str(
            chunk.get(
                "chunk_id",
                ""
            )
        )

        key = (
            source,
            page,
            chunk_id,
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(chunk)

    return result


# ==========================================================
# Build Context
# ==========================================================

def _build_context(
    chunks: List[Dict],
) -> str:

    context_parts = []

    for index, chunk in enumerate(
        chunks,
        start=1
    ):

        source = _source_display_name(
            chunk.get("source")
        )

        page = chunk.get(
            "page_number"
        )

        text = _clean_text(
            chunk.get("text")
        )

        if not text:
            continue

        context_parts.append(
            f"[SOURCE {index}]\n"
            f"Document: {source}\n"
            f"Page: {page}\n"
            f"Text:\n{text}"
        )

    return "\n\n".join(
        context_parts
    )


# ==========================================================
# Build Sources For UI
# ==========================================================

def _build_sources(
    chunks: List[Dict],
) -> List[Dict]:

    sources = []
    seen = set()

    for chunk in chunks:

        source = _source_display_name(
            chunk.get("source")
        )

        if not source:
            continue

        page = chunk.get(
            "page_number"
        )

        key = (
            _normalize_source(source),
            page,
        )

        if key in seen:
            continue

        seen.add(key)

        sources.append({
            "source": source,
            "page_number": page,
        })

    return sources


# ==========================================================
# Main RAG Function
# ==========================================================

def ask_rag(
    question: str,
    history: Optional[List[Dict]] = None,
) -> Dict:

    history = history or []

    if not question or not question.strip():

        return {
            "answer": "Please enter a question.",
            "sources": [],
            "retrieval_question": "",
        }

    print("\n" + "=" * 70)
    print("RAG REQUEST")
    print("=" * 70)

    print(
        "Question:",
        question
    )

    # ======================================================
    # 0. Greeting / Acknowledgement Detection
    #
    # Casual messages aren't document questions ΓÇö answer them
    # conversationally instead of running them through the
    # retrieval pipeline (which would incorrectly return
    # "I couldn't find that information").
    # ======================================================

    if _is_greeting(question):

        print("\nDetected greeting ΓÇö responding conversationally.")
        print("=" * 70)

        return {
            "answer": _greeting_response(),
            "sources": [],
            "retrieval_question": question,
        }

    if _is_acknowledgement(question):

        print("\nDetected acknowledgement ΓÇö responding conversationally.")
        print("=" * 70)

        return {
            "answer": _acknowledgement_response(),
            "sources": [],
            "retrieval_question": question,
        }

    # ======================================================
    # 1. Resolve Follow-Up
    # ======================================================

    resolved_question = question

    if history:

        print(
            "\nPrevious conversation found."
        )

        try:

            rewritten = rewrite_question(
                question,
                history
            )

            if rewritten and rewritten.strip():

                resolved_question = (
                    rewritten.strip()
                )

        except Exception as error:

            print(
                "Question rewriting failed:"
            )

            print(
                type(error).__name__,
                str(error)
            )

            resolved_question = question

    print(
        "\nRetrieval question:",
        resolved_question
    )

    # ======================================================
    # 2. Vector Retrieval
    # ======================================================

    vector_results = _vector_search(
        resolved_question,
        limit=VECTOR_LIMIT,
    )

    print(
        "\nQdrant results:",
        len(vector_results)
    )

    top_score = max(
        (doc.get("similarity", 0.0) for doc in vector_results),
        default=0.0,
    )

    keyword_match = _has_keyword_match(
        resolved_question,
        vector_results,
    )

    print(
        "\nTop similarity score:",
        f"{top_score:.4f}",
        "| keyword match:",
        keyword_match,
    )

    if not vector_results or (
        not keyword_match
        and top_score < MIN_VECTOR_SIMILARITY_NO_KEYWORD
    ):

        return {
            "answer": (
                "I couldn't find that information "
                "in the uploaded documents."
            ),
            "sources": [],
            "retrieval_question": resolved_question,
        }

    # ======================================================
    # 3. Select Target Document
    # ======================================================

    selected_source = _select_target_source(
        resolved_question,
        vector_results,
    )

    print(
        "\nSelected document:",
        selected_source
    )

    if not selected_source:

        return {
            "answer": (
                "I couldn't determine which uploaded "
                "document is relevant to your question."
            ),
            "sources": [],
            "retrieval_question": resolved_question,
        }

    # ======================================================
    # 4. Load BM25 Corpus
    # ======================================================

    all_documents = _load_all_documents()

    print(
        "\nTotal chunks:",
        len(all_documents)
    )

    # ======================================================
    # 5. Filter to selected document
    # ======================================================

    isolated_vector_results = (
        _filter_by_source(
            vector_results,
            selected_source
        )
    )

    isolated_documents = (
        _filter_by_source(
            all_documents,
            selected_source
        )
    )

    print(
        "Chunks from selected document:",
        len(isolated_documents)
    )

    print(
        "Vector chunks from selected document:",
        len(isolated_vector_results)
    )

    if not isolated_documents:

        return {
            "answer": (
                "I couldn't find usable content "
                "from the selected document."
            ),
            "sources": [],
            "retrieval_question": resolved_question,
        }

    # ======================================================
    # 6. Hybrid Retrieval
    # ======================================================

    hybrid = HybridRetriever(
        documents=isolated_documents,
        vector_results=isolated_vector_results,
    )

    hybrid_results = hybrid.search(
        query=resolved_question,
        top_k=HYBRID_TOP_K,
    )

    # ======================================================
    # 7. Final Source Safety Filter
    # ======================================================

    final_chunks = _filter_by_source(
        hybrid_results,
        selected_source
    )

    final_chunks = _deduplicate_chunks(
        final_chunks
    )

    final_chunks = final_chunks[
        :FINAL_TOP_K
    ]

    print(
        "\nFinal selected chunks:"
    )

    for index, chunk in enumerate(
        final_chunks,
        start=1
    ):

        print(
            f"[{index}] "
            f"{chunk.get('source')} | "
            f"Page {chunk.get('page_number')} | "
            f"Score "
            f"{chunk.get('hybrid_score', 0.0):.4f}"
        )

    if not final_chunks:

        return {
            "answer": (
                "I couldn't find that information "
                "in the uploaded documents."
            ),
            "sources": [],
            "retrieval_question": resolved_question,
        }

    # ======================================================
    # 8. Build Grounded Context
    # ======================================================

    context = _build_context(
        final_chunks
    )

    # ======================================================
    # 9. Generate Answer
    # ======================================================

    print(
        "\nGenerating grounded answer..."
    )

    answer = generate_answer(
        resolved_question,
        context,
    )

    # ======================================================
    # 9b. Hallucination Check
    # ======================================================

    groundedness = check_groundedness(answer, context)

    if groundedness["flagged"]:
        print(
            "\nΓÜá∩╕Å  GROUNDEDNESS WARNING ΓÇö score:",
            groundedness["groundedness_score"],
            "| missing claims:",
            groundedness["claims_missing"],
        )

    # ======================================================
    # 10. Sources
    # ======================================================

    sources = _build_sources(
        final_chunks
    )

    print(
        "\nFinal sources:"
    )

    for source in sources:

        print(
            f"- {source['source']} "
            f"| Page {source['page_number']}"
        )

    print("=" * 70)

    # ======================================================
    # 11. API Response
    # ======================================================

    return {
        "answer": answer,
        "sources": sources,
        "retrieval_question": resolved_question,
        "groundedness": groundedness,
    }
