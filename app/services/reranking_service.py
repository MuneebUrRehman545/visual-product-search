"""Service for lightweight second-stage visual re-ranking using HSV color distributions.

Combines primary semantic vector similarity with fine-grained color histogram matching.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_COLOR_FEATURES_PATH = PROJECT_ROOT / "artifacts" / "embeddings" / "color_features.npy"
DEFAULT_COLOR_IDS_PATH = PROJECT_ROOT / "artifacts" / "embeddings" / "color_catalog_ids.npy"

H_BINS = 32
S_BINS = 16
V_BINS = 16
FEATURE_DIM = H_BINS + S_BINS + V_BINS  # 64


def extract_hsv_histogram(image_source: Union[str, Path, Image.Image]) -> np.ndarray:
    """Extract a 64-dim L2-normalized HSV color histogram from an image."""
    if isinstance(image_source, (str, Path)):
        with Image.open(image_source) as img:
            rgb_img = img.convert("RGB")
    elif isinstance(image_source, Image.Image):
        rgb_img = image_source.convert("RGB")
    else:
        raise TypeError(f"Unsupported image source type: {type(image_source)}")

    # Downsample for fast, noise-tolerant color representation
    img_small = rgb_img.resize((64, 64)).convert("HSV")
    hsv_arr = np.array(img_small)

    h = hsv_arr[:, :, 0]
    s = hsv_arr[:, :, 1]
    v = hsv_arr[:, :, 2]

    h_hist, _ = np.histogram(h, bins=H_BINS, range=(0, 255))
    s_hist, _ = np.histogram(s, bins=S_BINS, range=(0, 255))
    v_hist, _ = np.histogram(v, bins=V_BINS, range=(0, 255))

    hist = np.concatenate([h_hist, s_hist, v_hist]).astype(np.float32)
    norm = np.linalg.norm(hist)
    return hist / (norm + 1e-7)


class ColorRerankingService:
    """Second-stage re-ranking service using precomputed color histograms."""

    def __init__(
        self,
        color_features_path: Path = DEFAULT_COLOR_FEATURES_PATH,
        color_ids_path: Path = DEFAULT_COLOR_IDS_PATH,
        default_color_weight: float = 0.20,
        default_initial_k: int = 50,
    ) -> None:
        self.color_features_path = color_features_path
        self.color_ids_path = color_ids_path
        self.default_color_weight = default_color_weight
        self.default_initial_k = default_initial_k

        self.features_by_id: Dict[int, np.ndarray] = {}
        self._load_features()

    def _load_features(self) -> None:
        """Load precomputed color features into memory indexed by catalog_item_id."""
        if self.color_features_path.exists() and self.color_ids_path.exists():
            features = np.load(str(self.color_features_path))
            ids = np.load(str(self.color_ids_path))
            for cid, feat in zip(ids, features):
                self.features_by_id[int(cid)] = feat

    def get_color_feature_by_id(self, catalog_item_id: int) -> Optional[np.ndarray]:
        """Retrieve precomputed color feature vector for a catalog item."""
        return self.features_by_id.get(int(catalog_item_id))

    def compute_color_similarity(self, query_feat: np.ndarray, catalog_feat: np.ndarray) -> float:
        """Compute cosine similarity between two normalized color vectors in [0, 1]."""
        dot = float(np.dot(query_feat, catalog_feat))
        # Clamp to [0, 1] range
        return max(0.0, min(1.0, (dot + 1.0) / 2.0))

    def rerank_results(
        self,
        query_image: Union[str, Path, Image.Image],
        candidate_items: List[Dict[str, Any]],
        color_weight: Optional[float] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Re-rank candidate search results by fusing semantic and color similarity scores."""
        if not candidate_items:
            return []

        w_color = color_weight if color_weight is not None else self.default_color_weight
        w_emb = 1.0 - w_color

        # If color weight is 0.0, preserve initial embedding ranking directly
        if w_color <= 0.0:
            return candidate_items[:top_k]

        # Extract query color feature
        query_color_feat = extract_hsv_histogram(query_image)

        scored_candidates: List[Tuple[float, Dict[str, Any]]] = []

        # Min-max scale initial embedding scores across candidates if available
        raw_emb_scores = [float(item.get("similarity_score", 1.0)) for item in candidate_items]
        min_emb = min(raw_emb_scores)
        max_emb = max(raw_emb_scores)
        emb_range = max_emb - min_emb if max_emb > min_emb else 1.0

        for item, raw_score in zip(candidate_items, raw_emb_scores):
            item_id = int(item["id"] if "id" in item else item.get("product_id", 0))
            cat_feat = self.get_color_feature_by_id(item_id)

            if cat_feat is None:
                # Fallback to computing on the fly if relative_path is available
                rel_path = item.get("relative_path") or item.get("image_path")
                if rel_path and (PROJECT_ROOT / rel_path).exists():
                    cat_feat = extract_hsv_histogram(PROJECT_ROOT / rel_path)
                else:
                    cat_feat = query_color_feat  # Neutral fallback

            color_sim = self.compute_color_similarity(query_color_feat, cat_feat)
            norm_emb_score = (raw_score - min_emb) / emb_range if emb_range > 0 else raw_score

            combined_score = (w_emb * norm_emb_score) + (w_color * color_sim)

            updated_item = dict(item)
            updated_item["semantic_score"] = round(raw_score, 4)
            updated_item["color_score"] = round(color_sim, 4)
            updated_item["combined_score"] = round(combined_score, 4)
            updated_item["similarity_score"] = round(combined_score, 4)

            scored_candidates.append((combined_score, updated_item))

        # Sort descending by combined score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        reranked_results = []
        for new_rank, (_, item) in enumerate(scored_candidates[:top_k], start=1):
            item["rank"] = new_rank
            reranked_results.append(item)

        return reranked_results
