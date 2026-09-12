"""Service for visual product search using ResNet-50 and FAISS IndexIDMap2."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import faiss
import numpy as np
from PIL import Image

from app.db.database import fetch_catalog_items_by_ids, get_database_url, get_db_path
from app.services.resnet_embedding_service import ResNet50EmbeddingService

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def resolve_resnet_index_path() -> Path:
    """Resolve ResNet FAISS index path with environment variable precedence."""
    # 1. Explicit full path to index
    env_exact_path = os.getenv("FAISS_RESNET_INDEX_PATH")
    if env_exact_path:
        p = Path(env_exact_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    # 2. Configured FAISS directory
    env_dir = os.getenv("FAISS_INDEX_DIR")
    if env_dir:
        p_dir = Path(env_dir)
        base = p_dir if p_dir.is_absolute() else PROJECT_ROOT / p_dir
        candidate = base / "resnet.index"
        if candidate.exists():
            return candidate

    # 3. Production artifacts location
    prod_path = PROJECT_ROOT / "artifacts" / "faiss" / "resnet.index"
    if prod_path.exists():
        return prod_path

    # 4. Legacy fallback location
    legacy_path = PROJECT_ROOT / "data" / "embeddings" / "resnet50" / "catalog.index"
    if legacy_path.exists():
        return legacy_path

    return prod_path


class ResNetSearchService:
    """Service for querying visual product similarity using ResNet50 embeddings and FAISS."""

    def __init__(
        self,
        index_path: Optional[Union[str, Path]] = None,
        db_path: Optional[Union[str, Path]] = None,
        database_url: Optional[str] = None,
        embedding_service: Optional[ResNet50EmbeddingService] = None,
    ) -> None:
        if index_path:
            self.index_path = Path(index_path)
        else:
            self.index_path = resolve_resnet_index_path()

        self.db_path = Path(db_path) if db_path else get_db_path()
        self.database_url = database_url if database_url else get_database_url()

        if not self.index_path.exists():
            raise FileNotFoundError(
                f"ResNet FAISS index file not found at: {self.index_path}. "
                f"Ensure artifacts/faiss/resnet.index is present or set FAISS_INDEX_DIR."
            )

        try:
            self.index = faiss.read_index(str(self.index_path))
        except Exception as e:
            raise RuntimeError(f"Failed to load FAISS index from {self.index_path}: {e}") from e

        self.embedding_service = (
            embedding_service if embedding_service is not None else ResNet50EmbeddingService()
        )

    def search(
        self,
        query_image: Union[str, Path, Image.Image],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search catalog for visually similar products given a query image using ResNet50."""
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
            (int(cid), float(score))
            for cid, score in zip(raw_ids, raw_scores)
            if cid != -1
        ]

        if not valid_matches:
            return []

        target_item_ids = [item_id for item_id, _ in valid_matches]
        scores_by_id = {item_id: score for item_id, score in valid_matches}

        # Order-preserving batch database lookup
        db_items = fetch_catalog_items_by_ids(
            target_item_ids,
            database_url=self.database_url,
            db_path=self.db_path,
        )

        results: List[Dict[str, Any]] = []
        for rank, item in enumerate(db_items, start=1):
            cid = item["id"]
            fn = item.get("filename") or f"{item.get('image_id')}.jpg"
            img_url = item.get("image_url") or f"/catalog-images/{fn}"

            results.append(
                {
                    "rank": rank,
                    "catalog_item_id": cid,
                    "id": cid,
                    "product_id": item.get("product_id", cid),
                    "external_id": str(item.get("external_id") or item.get("image_id") or cid),
                    "filename": fn,
                    "product_display_name": item.get("product_display_name"),
                    "category": item.get("category") or item.get("master_category"),
                    "sub_category": item.get("sub_category"),
                    "article_type": item.get("article_type"),
                    "base_colour": item.get("base_colour"),
                    "gender": item.get("gender"),
                    "season": item.get("season"),
                    "usage": item.get("usage"),
                    "image_url": img_url,
                    "similarity_score": round(scores_by_id.get(cid, 0.0), 4),
                }
            )

        return results

    def search_by_embedding(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search catalog for visually similar products given a precomputed embedding vector."""
        if not isinstance(top_k, int) or not (1 <= top_k <= 50):
            raise ValueError(f"top_k must be an integer between 1 and 50, got {top_k}")

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
            (int(cid), float(score))
            for cid, score in zip(raw_ids, raw_scores)
            if cid != -1
        ]

        if not valid_matches:
            return []

        target_item_ids = [item_id for item_id, _ in valid_matches]
        scores_by_id = {item_id: score for item_id, score in valid_matches}

        db_items = fetch_catalog_items_by_ids(
            target_item_ids,
            database_url=self.database_url,
            db_path=self.db_path,
        )

        results: List[Dict[str, Any]] = []
        for rank, item in enumerate(db_items, start=1):
            cid = item["id"]
            fn = item.get("filename") or f"{item.get('image_id')}.jpg"
            img_url = item.get("image_url") or f"/catalog-images/{fn}"

            results.append(
                {
                    "rank": rank,
                    "catalog_item_id": cid,
                    "id": cid,
                    "product_id": item.get("product_id", cid),
                    "external_id": str(item.get("external_id") or item.get("image_id") or cid),
                    "filename": fn,
                    "product_display_name": item.get("product_display_name"),
                    "category": item.get("category") or item.get("master_category"),
                    "sub_category": item.get("sub_category"),
                    "article_type": item.get("article_type"),
                    "base_colour": item.get("base_colour"),
                    "gender": item.get("gender"),
                    "season": item.get("season"),
                    "usage": item.get("usage"),
                    "image_url": img_url,
                    "similarity_score": round(scores_by_id.get(cid, 0.0), 4),
                }
            )

        return results
