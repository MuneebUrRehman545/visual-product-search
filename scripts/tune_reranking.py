"""Grid Search Parameter Tuning for Second-Stage Color Re-ranking.

Tuned strictly on the validation split (data/splits/validation_queries.csv).
Freezes the optimal parameters into evaluation/results/reranking_config.json.

Outputs:
  - evaluation/results/reranking_validation.csv
  - evaluation/results/reranking_config.json
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Set, Tuple
import faiss
import numpy as np
import open_clip
import pandas as pd
from PIL import Image
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.reranking_service import ColorRerankingService, extract_hsv_histogram

DEFAULT_GT_CSV = PROJECT_ROOT / "evaluation" / "ground_truth.csv"
DEFAULT_ID_MAP_CSV = PROJECT_ROOT / "data" / "manifests" / "catalog_id_map.csv"
CLIP_INDEX_PATH = PROJECT_ROOT / "artifacts" / "faiss" / "clip.index"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

OUTPUT_SWEEP_CSV = RESULTS_DIR / "reranking_validation.csv"
OUTPUT_CONFIG_JSON = RESULTS_DIR / "reranking_config.json"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Tune re-ranking parameters on validation set.")
    parser.add_argument(
        "--gt-csv",
        type=Path,
        default=DEFAULT_GT_CSV,
        help="Path to evaluation/ground_truth.csv",
    )
    parser.add_argument(
        "--id-map-csv",
        type=Path,
        default=DEFAULT_ID_MAP_CSV,
        help="Path to data/manifests/catalog_id_map.csv",
    )
    parser.add_argument(
        "--primary-metric",
        type=str,
        default="P@5",
        help="Primary metric to maximize (default: P@5)",
    )
    return parser.parse_args()


def compute_metrics_for_query(retrieved_ids: List[int], relevant_ids: Set[int], k_values: List[int] = [1, 5, 10]) -> Dict[str, float]:
    """Compute Precision, Recall, Hit-rate, and MRR for a single query."""
    metrics = {}
    num_rel = len(relevant_ids)
    if num_rel == 0:
        return {f"P@{k}": 0.0 for k in k_values} | {f"R@{k}": 0.0 for k in k_values} | {"MRR": 0.0}

    first_hit_rank = 0
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_ids:
            if first_hit_rank == 0:
                first_hit_rank = rank

    metrics["MRR"] = 1.0 / first_hit_rank if first_hit_rank > 0 else 0.0

    for k in k_values:
        top_k_ids = retrieved_ids[:k]
        hits = sum(1 for rid in top_k_ids if rid in relevant_ids)
        metrics[f"P@{k}"] = hits / k
        metrics[f"R@{k}"] = hits / num_rel
        metrics[f"Hit@{k}"] = 1.0 if hits > 0 else 0.0

    return metrics


def tune_reranking_parameters(
    gt_csv_path: Path,
    id_map_csv_path: Path,
    primary_metric: str = "P@5",
) -> Dict[str, Any]:
    """Execute grid search parameter sweep across validation queries."""
    start_time = time.time()
    print("=" * 70)
    print(" " * 14 + "RE-RANKING PARAMETER TUNING PIPELINE (VALIDATION)")
    print("=" * 70)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device:                 {device}")
    print(f"Primary Tuning Metric:  {primary_metric}")

    # 1. Load Ground Truth (Validation only) & ID Map
    df_gt = pd.read_csv(gt_csv_path)
    df_val = df_gt[df_gt["split"] == "validation"].copy()
    df_id_map = pd.read_csv(id_map_csv_path)

    img_to_cat_id = dict(zip(df_id_map["image_id"], df_id_map["catalog_item_id"]))
    print(f"Loaded {len(df_val)} validation queries for tuning.")

    # 2. Load FAISS Index, OpenCLIP model, and Re-ranking Service
    print("Loading FAISS CLIP index and Re-ranking Service...")
    clip_index = faiss.read_index(str(CLIP_INDEX_PATH))
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    model = model.to(device).eval()

    reranker = ColorRerankingService()

    # 3. Pre-extract all validation query vectors and coarse candidates (max initial_k = 100)
    print("Precomputing validation query embeddings and coarse FAISS Top-100 candidates...")
    val_query_data = []
    for _, row in df_val.iterrows():
        q_path = PROJECT_ROOT / row["query_path"]
        raw_rel_ids = [int(x.strip()) for x in str(row["relevant_catalog_ids"]).split(",") if x.strip().isdigit()]
        rel_cat_ids = set(img_to_cat_id[iid] for iid in raw_rel_ids if iid in img_to_cat_id)

        with Image.open(q_path) as img:
            rgb_img = img.convert("RGB")
            tensor = preprocess(rgb_img).unsqueeze(0).to(device)
            query_color_feat = extract_hsv_histogram(rgb_img)

        with torch.inference_mode():
            feat = model.encode_image(tensor)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            q_vec = feat.cpu().numpy().astype(np.float32)

        scores, ids = clip_index.search(q_vec, 100)
        coarse_candidates = []
        for sim, cid in zip(scores[0], ids[0]):
            coarse_candidates.append(
                {
                    "id": int(cid),
                    "similarity_score": float(sim),
                }
            )

        val_query_data.append(
            {
                "query_id": row["query_id"],
                "query_path": str(row["query_path"]),
                "relevant_ids": rel_cat_ids,
                "query_color_feat": query_color_feat,
                "coarse_candidates": coarse_candidates,
            }
        )

    # 4. Define Parameter Grid
    initial_k_grid = [20, 30, 50, 100]
    color_weight_grid = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]

    sweep_results = []
    best_config = None
    best_primary_score = -1.0
    best_tiebreak_score = -1.0

    print(f"\nRunning Parameter Grid Sweep ({len(initial_k_grid)} initial_k x {len(color_weight_grid)} weights = {len(initial_k_grid)*len(color_weight_grid)} configs)...")

    for k_init in initial_k_grid:
        for w_color in color_weight_grid:
            w_emb = 1.0 - w_color
            query_metric_records = []
            start_sweep_t = time.perf_counter()

            for q in val_query_data:
                candidates_subset = q["coarse_candidates"][:k_init]
                query_color_feat = q["query_color_feat"]
                rel_ids = q["relevant_ids"]

                if w_color == 0.0:
                    reranked = candidates_subset[:10]
                else:
                    # Score fusion
                    raw_emb_scores = [c["similarity_score"] for c in candidates_subset]
                    min_emb, max_emb = min(raw_emb_scores), max(raw_emb_scores)
                    emb_range = max_emb - min_emb if max_emb > min_emb else 1.0

                    scored = []
                    for c in candidates_subset:
                        cid = c["id"]
                        cat_feat = reranker.get_color_feature_by_id(cid)
                        if cat_feat is None:
                            cat_feat = query_color_feat
                        col_sim = reranker.compute_color_similarity(query_color_feat, cat_feat)
                        norm_emb = (c["similarity_score"] - min_emb) / emb_range if emb_range > 0 else c["similarity_score"]
                        comb = (w_emb * norm_emb) + (w_color * col_sim)
                        scored.append((comb, cid))

                    scored.sort(key=lambda x: x[0], reverse=True)
                    reranked = [{"id": cid} for _, cid in scored[:10]]

                retrieved_top10 = [item["id"] for item in reranked]
                m = compute_metrics_for_query(retrieved_top10, rel_ids, k_values=[1, 5, 10])
                query_metric_records.append(m)

            elapsed_ms = (time.perf_counter() - start_sweep_t) * 1000.0 / len(val_query_data)

            # Aggregate
            p1 = float(np.mean([r["P@1"] for r in query_metric_records]))
            p5 = float(np.mean([r["P@5"] for r in query_metric_records]))
            p10 = float(np.mean([r["P@10"] for r in query_metric_records]))
            r1 = float(np.mean([r["R@1"] for r in query_metric_records]))
            r5 = float(np.mean([r["R@5"] for r in query_metric_records]))
            r10 = float(np.mean([r["R@10"] for r in query_metric_records]))
            hit1 = float(np.mean([r["Hit@1"] for r in query_metric_records]))
            hit5 = float(np.mean([r["Hit@5"] for r in query_metric_records]))
            hit10 = float(np.mean([r["Hit@10"] for r in query_metric_records]))
            mrr = float(np.mean([r["MRR"] for r in query_metric_records]))

            res_entry = {
                "initial_k": k_init,
                "embedding_weight": round(w_emb, 2),
                "color_weight": round(w_color, 2),
                "P@1": round(p1, 4),
                "P@5": round(p5, 4),
                "P@10": round(p10, 4),
                "R@1": round(r1, 4),
                "R@5": round(r5, 4),
                "R@10": round(r10, 4),
                "Hit@1": round(hit1, 4),
                "Hit@5": round(hit5, 4),
                "Hit@10": round(hit10, 4),
                "MRR": round(mrr, 4),
                "rerank_latency_ms": round(elapsed_ms, 3),
            }
            sweep_results.append(res_entry)

            # Check best
            current_primary = res_entry[primary_metric]
            current_tiebreak = (res_entry["R@5"] + res_entry["MRR"]) / 2.0

            if (current_primary > best_primary_score) or (
                abs(current_primary - best_primary_score) < 1e-6 and current_tiebreak > best_tiebreak_score
            ):
                best_primary_score = current_primary
                best_tiebreak_score = current_tiebreak
                best_config = res_entry

    # 5. Save Sweep CSV & Selected Config JSON
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    df_sweep = pd.DataFrame(sweep_results)
    df_sweep.to_csv(OUTPUT_SWEEP_CSV, index=False)
    print(f"\nSaved full grid search results: {OUTPUT_SWEEP_CSV.relative_to(PROJECT_ROOT)}")

    # Freeze configuration
    frozen_config = {
        "status": "frozen_after_validation",
        "primary_tuning_metric": primary_metric,
        "selected_configuration": {
            "initial_k": best_config["initial_k"],
            "embedding_weight": best_config["embedding_weight"],
            "color_weight": best_config["color_weight"],
            "feature_type": "HSV_Histogram",
            "feature_dim": 64,
            "normalization": "min_max_embedding_linear_fusion",
        },
        "validation_metrics": {
            "P@1": best_config["P@1"],
            "P@5": best_config["P@5"],
            "P@10": best_config["P@10"],
            "R@1": best_config["R@1"],
            "R@5": best_config["R@5"],
            "R@10": best_config["R@10"],
            "Hit@1": best_config["Hit@1"],
            "Hit@5": best_config["Hit@5"],
            "Hit@10": best_config["Hit@10"],
            "MRR": best_config["MRR"],
        },
        "baseline_comparison": {
            "baseline_P@5": float(df_sweep[(df_sweep["color_weight"] == 0.0) & (df_sweep["initial_k"] == 50)]["P@5"].iloc[0]),
            "reranked_P@5": best_config["P@5"],
            "delta_P@5": round(best_config["P@5"] - float(df_sweep[(df_sweep["color_weight"] == 0.0) & (df_sweep["initial_k"] == 50)]["P@5"].iloc[0]), 4),
        },
        "frozen_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(OUTPUT_CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(frozen_config, f, indent=2)

    print(f"Saved frozen configuration:   {OUTPUT_CONFIG_JSON.relative_to(PROJECT_ROOT)}")

    # 6. Display Sweep Summary Table
    print("\n" + "=" * 70)
    print(" " * 18 + "RE-RANKING PARAMETER SWEEP HIGHLIGHTS")
    print("=" * 70)
    print(f"{'Initial K':<10} | {'Color W':<10} | {'P@1':<8} | {'P@5':<8} | {'R@5':<8} | {'Hit@5':<8} | {'MRR':<8}")
    print("-" * 70)
    for r in sweep_results[::3]:  # sample rows
        marker = " <-- BEST" if r == best_config else ""
        print(f"{r['initial_k']:<10} | {r['color_weight']:<10.2f} | {r['P@1']:<8.4f} | {r['P@5']:<8.4f} | {r['R@5']:<8.4f} | {r['Hit@5']:<8.4f} | {r['MRR']:<8.4f}{marker}")
    print("-" * 70)
    print(f"\nOptimal Config: initial_k={best_config['initial_k']}, embedding_weight={best_config['embedding_weight']}, color_weight={best_config['color_weight']}")
    print(f"Validation P@5: {best_config['P@5']:.4f} (Baseline: {frozen_config['baseline_comparison']['baseline_P@5']:.4f}, Delta: {frozen_config['baseline_comparison']['delta_P@5']:+.4f})")
    print(f"Validation R@5: {best_config['R@5']:.4f}, MRR: {best_config['MRR']:.4f}, Hit@5: {best_config['Hit@5']:.4f}")
    print("=" * 70)

    elapsed = time.time() - start_time
    print(f"\nRe-ranking tuning completed in {elapsed:.2f} seconds.")
    return frozen_config


if __name__ == "__main__":
    args = parse_args()
    tune_reranking_parameters(
        gt_csv_path=args.gt_csv,
        id_map_csv_path=args.id_map_csv,
        primary_metric=args.primary_metric,
    )
