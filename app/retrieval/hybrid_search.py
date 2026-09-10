from typing import List, Dict, Optional

from app.retrieval.bm25_search import BM25Retriever


class HybridRetriever:
    """
    Production hybrid retriever.

    Combines:
        1. Vector similarity results
        2. BM25 keyword results

    using Reciprocal Rank Fusion (RRF).

    Supports document isolation so unrelated documents cannot
    re-enter the result set through BM25 retrieval.
    """

    def __init__(
        self,
        documents: List[Dict],
        vector_results: List[Dict],
        allowed_sources: Optional[List[str]] = None,
    ):
        """
        Parameters
        ----------
        documents:
            Full document/chunk collection available for BM25.

        vector_results:
            Results already returned by vector search.

        allowed_sources:
            Optional list of document sources that BM25/vector
            results are allowed to return.

            Example:
                ["Umair.pdf"]

            If None, all sources are allowed.
        """

        self.allowed_sources = self._normalize_sources(
            allowed_sources
        )

        # --------------------------------------------------
        # Apply document isolation BEFORE BM25 is created
        # --------------------------------------------------

        if self.allowed_sources:
            self.documents = [
                document
                for document in documents
                if self._source_allowed(document)
            ]

            self.vector_results = [
                document
                for document in vector_results
                if self._source_allowed(document)
            ]

        else:
            self.documents = list(documents)
            self.vector_results = list(vector_results)

        # --------------------------------------------------
        # BM25 works only on the isolated document set
        # --------------------------------------------------

        self.bm25 = BM25Retriever(self.documents)

    # ======================================================
    # Source normalization
    # ======================================================

    @staticmethod
    def _normalize_source(source: object) -> str:
        """
        Normalize source names so values such as:

            Umair.pdf
            umair.pdf
            Umair.pdf.pdf

        can be compared consistently.
        """

        if source is None:
            return ""

        source = str(source).strip().replace("\\", "/")

        # Keep only filename
        source = source.split("/")[-1]

        # Remove accidental duplicate .pdf extension
        while source.lower().endswith(".pdf.pdf"):
            source = source[:-4]

        return source.lower()

    @classmethod
    def _normalize_sources(
        cls,
        sources: Optional[List[str]]
    ) -> List[str]:

        if not sources:
            return []

        normalized = []

        for source in sources:

            value = cls._normalize_source(source)

            if value and value not in normalized:
                normalized.append(value)

        return normalized

    def _source_allowed(
        self,
        document: Dict
    ) -> bool:

        if not self.allowed_sources:
            return True

        document_source = self._normalize_source(
            document.get("source", "")
        )

        return document_source in self.allowed_sources

    # ======================================================
    # Reciprocal Rank Fusion
    # ======================================================

    @staticmethod
    def _rrf_score(
        rank: int,
        k: int = 60
    ) -> float:
        """
        Reciprocal Rank Fusion score.

        rank starts at 1.
        """

        return 1.0 / (k + rank)

    # ======================================================
    # Hybrid Search
    # ======================================================

    def search(
        self,
        query: str,
        top_k: int = 6,
    ) -> List[Dict]:

        if not query or not query.strip():
            return []

        combined: Dict[str, Dict] = {}

        # ==================================================
        # 1. Vector results
        # ==================================================

        vector_rank = 0

        for document in self.vector_results:

            # Extra safety check
            if not self._source_allowed(document):
                continue

            vector_rank += 1

            key = self._document_key(document)

            if key not in combined:

                combined[key] = {
                    **document,

                    "vector_rank": vector_rank,
                    "bm25_rank": None,

                    "vector_score": float(
                        document.get(
                            "similarity",
                            document.get(
                                "score",
                                0.0
                            )
                        )
                    ),

                    "bm25_score": 0.0,

                    "hybrid_score": 0.0,
                }

            combined[key]["hybrid_score"] += (
                self._rrf_score(vector_rank)
            )

        # ==================================================
        # 2. BM25 results
        # ==================================================

        bm25_results = self.bm25.search(
            query,
            top_k=max(top_k * 3, 10)
        )

        bm25_rank = 0

        for document in bm25_results:

            # ------------------------------------------------
            # Critical document-isolation protection
            # ------------------------------------------------

            if not self._source_allowed(document):
                continue

            bm25_rank += 1

            key = self._document_key(document)

            bm25_score = float(
                document.get(
                    "bm25_score",
                    0.0
                )
            )

            if key not in combined:

                combined[key] = {
                    **document,

                    "vector_rank": None,
                    "bm25_rank": bm25_rank,

                    "vector_score": 0.0,
                    "bm25_score": bm25_score,

                    "hybrid_score": 0.0,
                }

            else:

                combined[key]["bm25_rank"] = bm25_rank

                combined[key]["bm25_score"] = bm25_score

            combined[key]["hybrid_score"] += (
                self._rrf_score(bm25_rank)
            )

        # ==================================================
        # 3. Sort
        # ==================================================

        ranked_results = sorted(
            combined.values(),
            key=lambda item: item["hybrid_score"],
            reverse=True
        )

        # ==================================================
        # 4. Final safety filter
        # ==================================================

        if self.allowed_sources:

            ranked_results = [
                result
                for result in ranked_results
                if self._source_allowed(result)
            ]

        # ==================================================
        # 5. Return top results
        # ==================================================

        return ranked_results[:top_k]

    # ======================================================
    # Stable document/chunk identity
    # ======================================================

    @classmethod
    def _document_key(
        cls,
        document: Dict
    ) -> str:

        source = cls._normalize_source(
            document.get(
                "source",
                "unknown"
            )
        )

        page = str(
            document.get(
                "page_number",
                "unknown"
            )
        )

        chunk_id = str(
            document.get(
                "chunk_id",
                "unknown"
            )
        )

        return (
            f"{source}::"
            f"{page}::"
            f"{chunk_id}"
        )
