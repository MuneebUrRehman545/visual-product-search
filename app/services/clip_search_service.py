"""Service for visual product search using CLIP ViT-B-32 and FAISS index."""

from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union
import faiss
import numpy as np
from PIL import Image

from app.db.database import get_connection, get_db_path
from app.services.embedding_service import EmbeddingService

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "embeddings" / "clip_vit_b32" / "catalog.index"


class CLIPSearchService:
    """Service for querying visual product similarity using CLIP ViT-B-32 embeddings and FAISS."""

    def __init__(
        self,
        index_path: Optional[Union[str, Path]] = None,
        db_path: Optional[Union[str, Path]] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> None:
        """Initialize CLIPSearchService by loading FAISS index and EmbeddingService.

        Args:
            index_path: Path to clip_vit_b32 catalog.index file.
            db_path: Path to SQLite catalog.db file.
            embedding_service: Optional pre-instantiated EmbeddingService instance.

        Raises:
            FileNotFoundError: If the specified index file does not exist.
            RuntimeError: If FAISS fails to read the index.
        """
        self.index_path = Path(index_path) if index_path else DEFAULT_INDEX_PATH
        self.db_path = Path(db_path) if db_path else get_db_path()

        if not self.index_path.exists():
            raise FileNotFoundError(f"CLIP FAISS index file not found at: {self.index_path}")

        try:
            self.index = faiss.read_index(str(self.index_path))
        except Exception as e:
            raise RuntimeError(f"Failed to load FAISS index from {self.index_path}: {e}") from e

        self.embedding_service = (
            embedding_service if embedding_service is not None else EmbeddingService()
        )

    def search(
        self,
        query_image: Union[str, Path, Image.Image],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search catalog for visually similar products given a query image.

        Args:
            query_image: File path (str/Path) or PIL Image instance.
            top_k: Number of nearest neighbors to return (1 to 50).

        Returns:
            List[Dict[str, Any]]: List of matching products sorted by similarity rank.
                Each dict contains: rank, product_id, external_id, filename, image_path,
                category, similarity_score.

        Raises:
            ValueError: If top_k is outside [1, 50] or image processing fails.
            FileNotFoundError: If image file or database file is missing.
            RuntimeError: If search or database retrieval fails.
        """
        if not isinstance(top_k, int) or not (1 <= top_k <= 50):
            raise ValueError(f"top_k must be an integer between 1 and 50, got {top_k}")

        query_embedding = self.embedding_service.generate_image_embedding(query_image)
        query_vector = np.ascontiguousarray(
            query_embedding.reshape(1, -1).astype(np.float32)
        )

        try:
            scores, faiss_ids = self.index.search(query_vector, top_k)
        except Exception as e:
            raise RuntimeError(f"FAISS index search failed: {e}") from e

        if len(scores) == 0 or len(faiss_ids) == 0:
            return []

        raw_scores = scores[0]
        raw_ids = faiss_ids[0]

        valid_matches = [
            (int(pid), float(score))
            for pid, score in zip(raw_ids, raw_scores)
            if pid != -1
        ]

        if not valid_matches:
            return []

        product_id_list = [pid for pid, _ in valid_matches]
        products_by_id = self._fetch_products_by_ids(product_id_list)

        results: List[Dict[str, Any]] = []
        for rank, (product_id, score) in enumerate(valid_matches, start=1):
            if product_id not in products_by_id:
                continue

            prod = products_by_id[product_id]
            results.append(
                {
                    "rank": rank,
                    "product_id": prod["id"],
                    "external_id": prod["external_id"],
                    "filename": prod["filename"],
                    "image_path": prod["image_path"],
                    "category": prod["category"],
                    "similarity_score": round(score, 6),
                }
            )

        return results

    def _fetch_products_by_ids(self, product_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Fetch products from SQLite by a list of primary key IDs.

        Args:
            product_ids: List of integer SQLite product IDs.

        Returns:
            Dict[int, Dict[str, Any]]: Map of product_id -> product dict.
        """
        if not product_ids:
            return {}

        placeholders = ",".join("?" for _ in product_ids)
        sql = f"""
        SELECT id, external_id, image_path, filename, category, embedding_dimension, created_at
        FROM products
        WHERE id IN ({placeholders});
        """
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(sql, product_ids)
                rows = cursor.fetchall()
                return {row["id"]: dict(row) for row in rows}
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to fetch product records from SQLite database: {e}") from e
