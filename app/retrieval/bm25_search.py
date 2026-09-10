from rank_bm25 import BM25Okapi


class BM25Retriever:
    """
    BM25 keyword retriever.

    Used alongside vector similarity search to improve
    retrieval for exact names, terms, numbers, and phrases.
    """

    def __init__(self, documents):
        self.documents = documents

        tokenized_documents = [
            self._tokenize(document["text"])
            for document in documents
        ]

        self.bm25 = BM25Okapi(tokenized_documents)

    @staticmethod
    def _tokenize(text):
        return str(text).lower().split()

    def search(self, query, top_k=10):
        """
        Return the top BM25 matching documents.
        """

        if not self.documents:
            return []

        query_tokens = self._tokenize(query)

        scores = self.bm25.get_scores(query_tokens)

        ranked_indexes = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]

        results = []

        for index in ranked_indexes:

            document = dict(self.documents[index])

            document["bm25_score"] = float(
                scores[index]
            )

            results.append(document)

        return results
