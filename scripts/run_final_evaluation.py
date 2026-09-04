"""Final Held-Out Evaluation on Clean and Messy Test Queries for Week 3.

Evaluates 8 conditions across 200 clean test queries and 200 messy test queries:
  1. CLIP baseline — clean test
  2. CLIP + reranking — clean test
  3. ResNet baseline — clean test
  4. ResNet + reranking — clean test
  5. CLIP baseline — messy test
  6. CLIP + reranking — messy test
  7. ResNet baseline — messy test
  8. ResNet + reranking — messy test

Outputs:
  - evaluation/results/final_clean_results.csv
  - evaluation/results/final_messy_results.csv
  - evaluation/results/final_per_query_results.csv
  - evaluation/results/final_summary.json
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
from torchvision.models import ResNet50_Weights, resnet50

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.reranking_service import ColorRerankingService, extract_hsv_histogram

DEFAULT_TEST_CSV = PROJECT_ROOT / "data" / "splits" / "test_queries.csv"
DEFAULT_MESSY_MANIFEST = PROJECT_ROOT / "evaluation" / "messy_query_manifest.csv"
DEFAULT_ID_MAP_CSV = PROJECT_ROOT / "data" / "manifests" / "catalog_id_map.csv"
DEFAULT_GT_CSV = PROJECT_ROOT / "evaluation" / "ground_truth.csv"

CLIP_INDEX_PATH = PROJECT_ROOT / "artifacts" / "faiss" / "clip.index"
RESNET_INDEX_PATH = PROJECT_ROOT / "artifacts" / "faiss" / "resnet.index"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

OUTPUT_CLEAN_CSV = RESULTS_DIR / "final_clean_results.csv"
OUTPUT_MESSY_CSV = RESULTS_DIR / "final_messy_results.csv"
OUTPUT_PER_QUERY_CSV = RESULTS_DIR / "final_per_query_results.csv"
OUTPUT_SUMMARY_JSON = RESULTS_DIR / "final_summary.json"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run final held-out clean and messy evaluation.")
    parser.add_argument(
        "--test-csv",
        type=Path,
        default=DEFAULT_TEST_CSV,
        help="Path to data/splits/test_queries.csv",
    )
    parser.add_argument(
        "--messy-manifest",
        type=Path,
        default=DEFAULT_MESSY_MANIFEST,
        help="Path to evaluation/messy_query_manifest.csv",
    )
    parser.add_argument(
        "--id-map-csv",
        type=Path,
        default=DEFAULT_ID_MAP_CSV,
        help="Path to data/manifests/catalog_id_map.csv",
    )
    parser.add_argument(
        "--gt-csv",
        type=Path,
        default=DEFAULT_GT_CSV,
        help="Path to evaluation/ground_truth.csv",
    )
    parser.add_argument(
        "--rerank-color-weight",
        type=float,
        default=0.20,
        help="Color weight for re-ranking condition (default: 0.20)",
    )
    parser.add_argument(
        "--rerank-initial-k",
        type=int,
        default=30,
        help="Initial coarse candidate pool for re-ranking (default: 30)",
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


def evaluate_dataset(
    model_name: str,
    use_reranking: bool,
    queries_data: List[Dict[str, Any]],
    faiss_index: Any,
    feature_extractor: Any,
    reranker: ColorRerankingService,
    device: torch.device,
    color_weight: float = 0.20,
    initial_k: int = 30,
    top_k: int = 10,
    condition_label: str = "",
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Evaluate one experimental condition over query dataset."""
    w_color = color_weight if use_reranking else 0.0
    w_emb = 1.0 - w_color
    k_search = initial_k if use_reranking else top_k

    per_query_records = []
    total_emb_time = 0.0
    total_search_time = 0.0
    total_rerank_time = 0.0

    for q in queries_data:
        q_path = q["full_path"]
        rel_ids = q["relevant_catalog_item_ids"]

        # 1. Feature Extraction
        t0 = time.perf_counter()
        q_vec = feature_extractor(q_path)
        t1 = time.perf_counter()
        emb_ms = (t1 - t0) * 1000.0
        total_emb_time += emb_ms

        # 2. FAISS Retrieval
        t2 = time.perf_counter()
        scores, ids = faiss_index.search(q_vec, k_search)
        t3 = time.perf_counter()
        search_ms = (t3 - t2) * 1000.0
        total_search_time += search_ms

        # 3. Optional Re-ranking
        t4 = time.perf_counter()
        if use_reranking and w_color > 0.0:
            query_color_feat = extract_hsv_histogram(q_path)
            raw_scores = scores[0]
            min_s, max_s = min(raw_scores), max(raw_scores)
            s_range = max_s - min_s if max_s > min_s else 1.0

            scored = []
            for cid, raw_s in zip(ids[0], raw_scores):
                cid_int = int(cid)
                cat_feat = reranker.get_color_feature_by_id(cid_int)
                if cat_feat is None:
                    cat_feat = query_color_feat
                col_sim = reranker.compute_color_similarity(query_color_feat, cat_feat)
                norm_emb = (raw_s - min_s) / s_range if s_range > 0 else raw_s
                comb = (w_emb * norm_emb) + (w_color * col_sim)
                scored.append((comb, cid_int))

            scored.sort(key=lambda x: x[0], reverse=True)
            retrieved_ids = [cid for _, cid in scored[:top_k]]
        else:
            retrieved_ids = [int(x) for x in ids[0][:top_k]]

        t5 = time.perf_counter()
        rerank_ms = (t5 - t4) * 1000.0
        total_rerank_time += rerank_ms

        # Compute Metrics
        m = compute_metrics_for_query(retrieved_ids, rel_ids, k_values=[1, 5, 10])
        hits_5 = sum(1 for rid in retrieved_ids[:5] if rid in rel_ids)

        rec = {
            "condition": condition_label,
            "model": model_name,
            "reranked": use_reranking,
            "query_type": q.get("query_type", "clean"),
            "variation_type": q.get("variation_type", "clean"),
            "query_id": q["query_id"],
            "query_path": q["rel_path"],
            "category": q.get("category", ""),
            "relevant_count": len(rel_ids),
            "relevant_catalog_item_ids": list(rel_ids),
            "retrieved_catalog_item_ids": retrieved_ids,
            "hits_top5": hits_5,
            "P@1": round(m["P@1"], 4),
            "P@5": round(m["P@5"], 4),
            "P@10": round(m["P@10"], 4),
            "R@1": round(m["R@1"], 4),
            "R@5": round(m["R@5"], 4),
            "R@10": round(m["R@10"], 4),
            "Hit@1": m["Hit@1"],
            "Hit@5": m["Hit@5"],
            "Hit@10": m["Hit@10"],
            "MRR": round(m["MRR"], 4),
            "embedding_latency_ms": round(emb_ms, 2),
            "search_latency_ms": round(search_ms, 2),
            "rerank_latency_ms": round(rerank_ms, 3),
            "total_latency_ms": round(emb_ms + search_ms + rerank_ms, 2),
        }
        per_query_records.append(rec)

    n = len(per_query_records)
    summary = {
        "condition": condition_label,
        "model": model_name,
        "reranked": use_reranking,
        "query_type": queries_data[0].get("query_type", "clean"),
        "num_queries": n,
        "metrics": {
            "P@1": round(float(np.mean([r["P@1"] for r in per_query_records])), 4),
            "P@5": round(float(np.mean([r["P@5"] for r in per_query_records])), 4),
            "P@10": round(float(np.mean([r["P@10"] for r in per_query_records])), 4),
            "R@1": round(float(np.mean([r["R@1"] for r in per_query_records])), 4),
            "R@5": round(float(np.mean([r["R@5"] for r in per_query_records])), 4),
            "R@10": round(float(np.mean([r["R@10"] for r in per_query_records])), 4),
            "Hit@1": round(float(np.mean([r["Hit@1"] for r in per_query_records])), 4),
            "Hit@5": round(float(np.mean([r["Hit@5"] for r in per_query_records])), 4),
            "Hit@10": round(float(np.mean([r["Hit@10"] for r in per_query_records])), 4),
            "MRR": round(float(np.mean([r["MRR"] for r in per_query_records])), 4),
        },
        "latency_ms": {
            "avg_embedding_ms": round(total_emb_time / n, 2),
            "avg_search_ms": round(total_search_time / n, 3),
            "avg_rerank_ms": round(total_rerank_time / n, 3),
            "avg_total_ms": round((total_emb_time + total_search_time + total_rerank_time) / n, 2),
        },
    }

    return summary, per_query_records


def run_full_final_evaluation(
    test_csv_path: Path,
    messy_manifest_path: Path,
    id_map_csv_path: Path,
    gt_csv_path: Path,
    rerank_color_weight: float = 0.20,
    rerank_initial_k: int = 30,
) -> None:
    """Execute complete 8-condition final held-out evaluation."""
    start_time = time.time()
    print("=" * 70)
    print(" " * 12 + "FINAL HELD-OUT EVALUATION (CLEAN & MESSY)")
    print("=" * 70)

    num_cpus = os.cpu_count() or 4
    torch.set_num_threads(num_cpus)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load Ground Truth and ID Map
    df_gt = pd.read_csv(gt_csv_path)
    df_id_map = pd.read_csv(id_map_csv_path)
    df_test_clean = pd.read_csv(test_csv_path)
    df_messy = pd.read_csv(messy_manifest_path)

    img_to_cat_id = dict(zip(df_id_map["image_id"], df_id_map["catalog_item_id"]))
    gt_map = {r["query_id"]: str(r["relevant_catalog_ids"]) for _, r in df_gt.iterrows()}

    # Prepare Clean Query Data (200 items)
    clean_query_data = []
    for _, r in df_test_clean.iterrows():
        qid = r["query_id"]
        rel_ids_raw = gt_map.get(qid, "")
        raw_list = [int(x) for x in rel_ids_raw.split(",") if x.strip().isdigit()]
        rel_cat_ids = set(img_to_cat_id[iid] for iid in raw_list if iid in img_to_cat_id)
        clean_query_data.append(
            {
                "query_id": qid,
                "rel_path": r["relative_path"],
                "full_path": PROJECT_ROOT / r["relative_path"],
                "category": r.get("category", ""),
                "query_type": "clean",
                "variation_type": "clean",
                "relevant_catalog_item_ids": rel_cat_ids,
            }
        )

    # Prepare Messy Query Data (200 items)
    messy_query_data = []
    for _, r in df_messy.iterrows():
        qid = r["query_id"]
        rel_ids_raw = r["relevant_catalog_ids"]
        raw_list = [int(x) for x in str(rel_ids_raw).split(",") if x.strip().isdigit()]
        rel_cat_ids = set(img_to_cat_id[iid] for iid in raw_list if iid in img_to_cat_id)
        messy_query_data.append(
            {
                "query_id": qid,
                "rel_path": r["messy_image_path"],
                "full_path": PROJECT_ROOT / r["messy_image_path"],
                "category": r.get("category", ""),
                "query_type": "messy",
                "variation_type": r.get("variation_type", "messy"),
                "relevant_catalog_item_ids": rel_cat_ids,
            }
        )

    print(f"Clean Test Queries: {len(clean_query_data):,}")
    print(f"Messy Test Queries: {len(messy_query_data):,}")

    # 2. Load FAISS Indices, Models & Re-ranking Service
    print("\nLoading models and FAISS search indices...")
    clip_index = faiss.read_index(str(CLIP_INDEX_PATH))
    resnet_index = faiss.read_index(str(RESNET_INDEX_PATH))

    # OpenCLIP
    clip_model, _, clip_preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    clip_model = clip_model.to(device).eval()

    def clip_extractor(p):
        with Image.open(p) as img:
            t = clip_preprocess(img.convert("RGB")).unsqueeze(0).to(device)
        with torch.inference_mode():
            feat = clip_model.encode_image(t)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat.cpu().numpy().astype(np.float32)

    # ResNet-50
    rn_weights = ResNet50_Weights.DEFAULT
    rn_full = resnet50(weights=rn_weights)
    rn_feature_extractor = torch.nn.Sequential(*list(rn_full.children())[:-1]).to(device).eval()
    rn_preprocess = rn_weights.transforms()

    def resnet_extractor(p):
        with Image.open(p) as img:
            t = rn_preprocess(img.convert("RGB")).unsqueeze(0).to(device)
        with torch.inference_mode():
            feat = rn_feature_extractor(t)
            feat = torch.flatten(feat, 1)
            feat = feat / feat.norm(p=2, dim=-1, keepdim=True)
        return feat.cpu().numpy().astype(np.float32)

    reranker = ColorRerankingService()

    # 3. Execute 8 Evaluation Matrix Runs
    conditions = [
        ("CLIP baseline — clean test", "CLIP", False, clean_query_data, clip_index, clip_extractor),
        ("CLIP + reranking — clean test", "CLIP", True, clean_query_data, clip_index, clip_extractor),
        ("ResNet baseline — clean test", "ResNet-50", False, clean_query_data, resnet_index, resnet_extractor),
        ("ResNet + reranking — clean test", "ResNet-50", True, clean_query_data, resnet_index, resnet_extractor),
        ("CLIP baseline — messy test", "CLIP", False, messy_query_data, clip_index, clip_extractor),
        ("CLIP + reranking — messy test", "CLIP", True, messy_query_data, clip_index, clip_extractor),
        ("ResNet baseline — messy test", "ResNet-50", False, messy_query_data, resnet_index, resnet_extractor),
        ("ResNet + reranking — messy test", "ResNet-50", True, messy_query_data, resnet_index, resnet_extractor),
    ]

    all_summaries = []
    all_per_query = []

    print("\nRunning Evaluation Matrix across 8 conditions...")
    for label, m_name, is_rerank, q_dataset, idx, ext in conditions:
        print(f"  --> Running: {label}...")
        s, pq = evaluate_dataset(
            model_name=m_name,
            use_reranking=is_rerank,
            queries_data=q_dataset,
            faiss_index=idx,
            feature_extractor=ext,
            reranker=reranker,
            device=device,
            color_weight=rerank_color_weight,
            initial_k=rerank_initial_k,
            top_k=10,
            condition_label=label,
        )
        all_summaries.append(s)
        all_per_query.extend(pq)

    # 4. Save Final CSV and JSON Artifacts
    df_all_per_query = pd.DataFrame(all_per_query)
    df_all_per_query.to_csv(OUTPUT_PER_QUERY_CSV, index=False)

    df_clean_results = df_all_per_query[df_all_per_query["query_type"] == "clean"]
    df_clean_results.to_csv(OUTPUT_CLEAN_CSV, index=False)

    df_messy_results = df_all_per_query[df_all_per_query["query_type"] == "messy"]
    df_messy_results.to_csv(OUTPUT_MESSY_CSV, index=False)

    # Compute Messy Transformation Breakdown
    messy_transform_breakdown = {}
    for t_type in df_messy_results["variation_type"].unique():
        sub_df = df_messy_results[df_messy_results["variation_type"] == t_type]
        messy_transform_breakdown[t_type] = {
            "CLIP_P@5": round(float(sub_df[(sub_df["model"] == "CLIP") & (~sub_df["reranked"])]["P@5"].mean()), 4),
            "CLIP_R@5": round(float(sub_df[(sub_df["model"] == "CLIP") & (~sub_df["reranked"])]["R@5"].mean()), 4),
            "CLIP_Hit@5": round(float(sub_df[(sub_df["model"] == "CLIP") & (~sub_df["reranked"])]["Hit@5"].mean()), 4),
            "ResNet_P@5": round(float(sub_df[(sub_df["model"] == "ResNet-50") & (~sub_df["reranked"])]["P@5"].mean()), 4),
            "ResNet_R@5": round(float(sub_df[(sub_df["model"] == "ResNet-50") & (~sub_df["reranked"])]["R@5"].mean()), 4),
            "ResNet_Hit@5": round(float(sub_df[(sub_df["model"] == "ResNet-50") & (~sub_df["reranked"])]["Hit@5"].mean()), 4),
        }

    final_payload = {
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_summary": {
            "catalog_items": len(df_id_map),
            "clean_test_queries": len(clean_query_data),
            "messy_test_queries": len(messy_query_data),
        },
        "condition_summaries": all_summaries,
        "messy_transformation_breakdown": messy_transform_breakdown,
    }

    with open(OUTPUT_SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2)

    print(f"\nSaved final evaluation artifacts:")
    print(f"  + Clean Results CSV:  {OUTPUT_CLEAN_CSV.relative_to(PROJECT_ROOT)}")
    print(f"  + Messy Results CSV:  {OUTPUT_MESSY_CSV.relative_to(PROJECT_ROOT)}")
    print(f"  + Per-Query CSV:      {OUTPUT_PER_QUERY_CSV.relative_to(PROJECT_ROOT)}")
    print(f"  + Summary JSON:       {OUTPUT_SUMMARY_JSON.relative_to(PROJECT_ROOT)}")

    # 5. Display Complete Comparative Table
    print("\n" + "=" * 90)
    print(" " * 28 + "FINAL EVALUATION MATRIX SUMMARY")
    print("=" * 90)
    header = f"{'Condition':<35} | {'P@1':<7} | {'P@5':<7} | {'P@10':<7} | {'R@1':<7} | {'R@5':<7} | {'Hit@5':<7} | {'MRR':<7} | {'Lat(ms)':<7}"
    print(header)
    print("-" * 90)
    for s in all_summaries:
        m = s["metrics"]
        lat = s["latency_ms"]["avg_total_ms"]
        print(f"{s['condition']:<35} | {m['P@1']:<7.4f} | {m['P@5']:<7.4f} | {m['P@10']:<7.4f} | {m['R@1']:<7.4f} | {m['R@5']:<7.4f} | {m['Hit@5']:<7.4f} | {m['MRR']:<7.4f} | {lat:<7.1f}")
    print("=" * 90)

    # Display Transformation Breakdown
    print("\n" + "=" * 90)
    print(" " * 24 + "MESSY TEST BREAKDOWN BY TRANSFORMATION TYPE")
    print("=" * 90)
    print(f"{'Transformation Type':<25} | {'CLIP P@5':<10} | {'CLIP R@5':<10} | {'CLIP Hit@5':<12} | {'ResNet P@5':<10} | {'ResNet R@5':<10}")
    print("-" * 90)
    for t_name, b_data in messy_transform_breakdown.items():
        print(f"{t_name:<25} | {b_data['CLIP_P@5']:<10.4f} | {b_data['CLIP_R@5']:<10.4f} | {b_data['CLIP_Hit@5']:<12.4f} | {b_data['ResNet_P@5']:<10.4f} | {b_data['ResNet_R@5']:<10.4f}")
    print("=" * 90)

    elapsed = time.time() - start_time
    print(f"\nFinal evaluation completed in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    args = parse_args()
    run_full_final_evaluation(
        test_csv_path=args.test_csv,
        messy_manifest_path=args.messy_manifest,
        id_map_csv_path=args.id_map_csv,
        gt_csv_path=args.gt_csv,
        rerank_color_weight=args.rerank_color_weight,
        rerank_initial_k=args.rerank_initial_k,
    )
