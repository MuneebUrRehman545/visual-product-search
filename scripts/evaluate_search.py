"""Unified Baseline Evaluation for CLIP and ResNet-50 using Stable Catalog IDs.

Evaluates CLIP and ResNet models on the validation split before re-ranking.
Compares FAISS-returned catalog_item IDs directly against resolved ground-truth catalog_item IDs.

Outputs:
  - evaluation/results/clip_baseline_validation.json
  - evaluation/results/resnet_baseline_validation.json
  - evaluation/results/baseline_validation_per_query.csv
"""

import argparse
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

# Ensure workspace root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_catalog_items_by_ids

DEFAULT_GT_CSV = PROJECT_ROOT / "evaluation" / "ground_truth.csv"
DEFAULT_ID_MAP_CSV = PROJECT_ROOT / "data" / "manifests" / "catalog_id_map.csv"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

CLIP_INDEX_PATH = PROJECT_ROOT / "artifacts" / "faiss" / "clip.index"
RESNET_INDEX_PATH = PROJECT_ROOT / "artifacts" / "faiss" / "resnet.index"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Evaluate baseline search models.")
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
        "--split",
        type=str,
        default="validation",
        choices=["validation", "test", "all"],
        help="Split to evaluate (default: validation)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Maximum Top-K retrieval depth (default: 10)",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory to save evaluation result JSONs and CSV",
    )
    return parser.parse_args()


def load_clip_model(device: torch.device) -> Tuple[Any, Any]:
    """Load OpenCLIP model and preprocess."""
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    model = model.to(device).eval()
    return model, preprocess


def load_resnet_model(device: torch.device) -> Tuple[Any, Any]:
    """Load ResNet-50 feature extractor and transform."""
    weights = ResNet50_Weights.DEFAULT
    full_model = resnet50(weights=weights)
    feature_extractor = torch.nn.Sequential(*list(full_model.children())[:-1]).to(device).eval()
    preprocess = weights.transforms()
    return feature_extractor, preprocess


def extract_clip_query_embedding(img_path: Path, model: Any, preprocess: Any, device: torch.device) -> np.ndarray:
    """Extract L2-normalized 512-dim CLIP query vector."""
    with Image.open(img_path) as img:
        tensor = preprocess(img.convert("RGB")).unsqueeze(0).to(device)
    with torch.inference_mode():
        feat = model.encode_image(tensor)
        feat = feat / feat.norm(dim=-1, keepdim=True)
    return feat.cpu().numpy().astype(np.float32)


def extract_resnet_query_embedding(img_path: Path, model: Any, preprocess: Any, device: torch.device) -> np.ndarray:
    """Extract L2-normalized 2048-dim ResNet-50 query vector."""
    with Image.open(img_path) as img:
        tensor = preprocess(img.convert("RGB")).unsqueeze(0).to(device)
    with torch.inference_mode():
        feat = model(tensor)
        feat = torch.flatten(feat, 1)
        feat = feat / feat.norm(p=2, dim=-1, keepdim=True)
    return feat.cpu().numpy().astype(np.float32)


def compute_metrics_for_query(retrieved_ids: List[int], relevant_ids: Set[int], k_values: List[int] = [1, 5, 10]) -> Dict[str, float]:
    """Compute Precision@K, Recall@K, Hit@K, and MRR for a single query."""
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


def evaluate_model(
    model_name: str,
    gt_df: pd.DataFrame,
    id_map_df: pd.DataFrame,
    faiss_index_path: Path,
    device: torch.device,
    top_k: int = 10,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Run full evaluation over query dataset for a given model."""
    print(f"\nEvaluating Model: {model_name} (Total Queries: {len(gt_df):,})")

    # Map source image_id to stable catalog_item_id
    img_to_cat_id = dict(zip(id_map_df["image_id"], id_map_df["catalog_item_id"]))
    all_valid_cat_ids = set(id_map_df["catalog_item_id"].astype(int))

    # Load FAISS index
    if not faiss_index_path.exists():
        raise FileNotFoundError(f"FAISS index not found: {faiss_index_path}")
    index = faiss.read_index(str(faiss_index_path))

    # Load model
    if model_name == "CLIP":
        model, preprocess = load_clip_model(device)
        extractor = lambda p: extract_clip_query_embedding(p, model, preprocess, device)
    else:
        model, preprocess = load_resnet_model(device)
        extractor = lambda p: extract_resnet_query_embedding(p, model, preprocess, device)

    per_query_records = []
    total_emb_time = 0.0
    total_search_time = 0.0

    for _, row in gt_df.iterrows():
        qid = row["query_id"]
        q_path = PROJECT_ROOT / row["query_path"]
        raw_rel_ids = [int(x.strip()) for x in str(row["relevant_catalog_ids"]).split(",") if x.strip().isdigit()]
        rel_cat_ids = set(img_to_cat_id[iid] for iid in raw_rel_ids if iid in img_to_cat_id)

        # 1. Embedding latency
        t0 = time.perf_counter()
        q_vec = extractor(q_path)
        t1 = time.perf_counter()
        emb_lat_ms = (t1 - t0) * 1000.0
        total_emb_time += emb_lat_ms

        # 2. FAISS search latency
        t2 = time.perf_counter()
        scores, ids = index.search(q_vec, top_k)
        t3 = time.perf_counter()
        search_lat_ms = (t3 - t2) * 1000.0
        total_search_time += search_lat_ms

        retrieved_ids = [int(x) for x in ids[0]]
        
        # Verify returned IDs exist in catalog
        for ret_id in retrieved_ids:
            assert ret_id in all_valid_cat_ids, f"Returned ID {ret_id} not in catalog ID map!"

        # Metrics
        q_metrics = compute_metrics_for_query(retrieved_ids, rel_cat_ids, k_values=[1, 5, 10])
        hits_5 = sum(1 for rid in retrieved_ids[:5] if rid in rel_cat_ids)

        rec = {
            "model": model_name,
            "query_id": qid,
            "query_path": str(row["query_path"]),
            "category": row.get("category", ""),
            "relevant_count": len(rel_cat_ids),
            "relevant_catalog_item_ids": list(rel_cat_ids),
            "retrieved_catalog_item_ids": retrieved_ids,
            "hits_top5": hits_5,
            "P@1": round(q_metrics["P@1"], 4),
            "P@5": round(q_metrics["P@5"], 4),
            "P@10": round(q_metrics["P@10"], 4),
            "R@1": round(q_metrics["R@1"], 4),
            "R@5": round(q_metrics["R@5"], 4),
            "R@10": round(q_metrics["R@10"], 4),
            "Hit@1": q_metrics["Hit@1"],
            "Hit@5": q_metrics["Hit@5"],
            "Hit@10": q_metrics["Hit@10"],
            "MRR": round(q_metrics["MRR"], 4),
            "embedding_latency_ms": round(emb_lat_ms, 2),
            "search_latency_ms": round(search_lat_ms, 2),
            "total_latency_ms": round(emb_lat_ms + search_lat_ms, 2),
        }
        per_query_records.append(rec)

    # Compute aggregate summary
    n = len(per_query_records)
    summary = {
        "model": model_name,
        "split": gt_df["split"].iloc[0] if "split" in gt_df else "validation",
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
            "avg_embedding_latency_ms": round(total_emb_time / n, 2),
            "avg_faiss_search_latency_ms": round(total_search_time / n, 3),
            "avg_total_query_latency_ms": round((total_emb_time + total_search_time) / n, 2),
        },
    }

    return summary, per_query_records


def run_baseline_evaluation(
    gt_csv_path: Path,
    id_map_csv_path: Path,
    split: str = "validation",
    top_k: int = 10,
    results_dir: Path = DEFAULT_RESULTS_DIR,
) -> None:
    """Execute unified baseline evaluation for CLIP and ResNet-50."""
    start_time = time.time()
    print("=" * 70)
    print(" " * 16 + "UNIFIED BASELINE EVALUATION PIPELINE")
    print("=" * 70)

    num_cpus = os.cpu_count() or 4
    torch.set_num_threads(num_cpus)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    results_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Ground Truth and ID Map
    df_gt = pd.read_csv(gt_csv_path)
    df_id_map = pd.read_csv(id_map_csv_path)

    # Filter to requested split
    if split != "all":
        df_eval = df_gt[df_gt["split"] == split].copy()
    else:
        df_eval = df_gt.copy()

    print(f"Target Split:       {split.upper()} ({len(df_eval):,} queries)")
    print(f"Catalog ID Map:     {id_map_csv_path.relative_to(PROJECT_ROOT)} ({len(df_id_map):,} items)")
    print(f"Device:             {device} (Threads: {num_cpus})")

    # 2. Evaluate CLIP Baseline
    clip_summary, clip_per_query = evaluate_model(
        model_name="CLIP",
        gt_df=df_eval,
        id_map_df=df_id_map,
        faiss_index_path=CLIP_INDEX_PATH,
        device=device,
        top_k=top_k,
    )

    # 3. Evaluate ResNet-50 Baseline
    resnet_summary, resnet_per_query = evaluate_model(
        model_name="ResNet-50",
        gt_df=df_eval,
        id_map_df=df_id_map,
        faiss_index_path=RESNET_INDEX_PATH,
        device=device,
        top_k=top_k,
    )

    # 4. Save JSON and CSV results
    clip_json_path = results_dir / "clip_baseline_validation.json"
    resnet_json_path = results_dir / "resnet_baseline_validation.json"
    per_query_csv_path = results_dir / "baseline_validation_per_query.csv"

    with open(clip_json_path, "w", encoding="utf-8") as f:
        json.dump(clip_summary, f, indent=2)

    with open(resnet_json_path, "w", encoding="utf-8") as f:
        json.dump(resnet_summary, f, indent=2)

    df_combined_per_query = pd.DataFrame(clip_per_query + resnet_per_query)
    df_combined_per_query.to_csv(per_query_csv_path, index=False)

    print(f"\nSaved evaluation artifacts:")
    print(f"  + CLIP Summary:   {clip_json_path.relative_to(PROJECT_ROOT)}")
    print(f"  + ResNet Summary: {resnet_json_path.relative_to(PROJECT_ROOT)}")
    print(f"  + Per-Query CSV:  {per_query_csv_path.relative_to(PROJECT_ROOT)}")

    # 5. Print Sample Per-Query Verification
    print("\n" + "=" * 70)
    print(" " * 20 + "SAMPLE QUERY VERIFICATION (Top 5 Queries)")
    print("=" * 70)
    for q_idx in range(min(5, len(clip_per_query))):
        c_rec = clip_per_query[q_idx]
        r_rec = resnet_per_query[q_idx]
        qid = c_rec["query_id"]
        q_rel = c_rec["relevant_catalog_item_ids"]
        print(f"\nQuery [{qid}]: {c_rec['query_path']} | Category: {c_rec['category']}")
        print(f"  Relevant Catalog Item IDs ({len(q_rel)}): {q_rel}")
        print(f"  [CLIP]      Top 5 IDs: {c_rec['retrieved_catalog_item_ids'][:5]} | Hits: {c_rec['hits_top5']} | P@5: {c_rec['P@5']:.4f} | R@5: {c_rec['R@5']:.4f} | MRR: {c_rec['MRR']:.4f}")
        print(f"  [ResNet-50] Top 5 IDs: {r_rec['retrieved_catalog_item_ids'][:5]} | Hits: {r_rec['hits_top5']} | P@5: {r_rec['P@5']:.4f} | R@5: {r_rec['R@5']:.4f} | MRR: {r_rec['MRR']:.4f}")

    # 6. Print Comparative Summary Table
    print("\n" + "=" * 70)
    print(" " * 18 + "BASELINE VALIDATION METRICS COMPARISON")
    print("=" * 70)
    print(f"{'Metric':<15} | {'CLIP (ViT-B/32)':<18} | {'ResNet-50':<18} | {'Delta (CLIP vs ResNet)':<20}")
    print("-" * 75)
    for metric_key in ["P@1", "P@5", "P@10", "R@1", "R@5", "R@10", "Hit@1", "Hit@5", "Hit@10", "MRR"]:
        c_val = clip_summary["metrics"][metric_key]
        r_val = resnet_summary["metrics"][metric_key]
        diff = c_val - r_val
        diff_str = f"{diff:+.4f}"
        print(f"{metric_key:<15} | {c_val:<18.4f} | {r_val:<18.4f} | {diff_str:<20}")
    print("-" * 75)
    print(f"{'Avg Emb Latency':<15} | {clip_summary['latency_ms']['avg_embedding_latency_ms']:<15.2f} ms | {resnet_summary['latency_ms']['avg_embedding_latency_ms']:<15.2f} ms |")
    print(f"{'Avg FAISS Latency':<15} | {clip_summary['latency_ms']['avg_faiss_search_latency_ms']:<15.3f} ms | {resnet_summary['latency_ms']['avg_faiss_search_latency_ms']:<15.3f} ms |")
    print(f"{'Total Latency':<15} | {clip_summary['latency_ms']['avg_total_query_latency_ms']:<15.2f} ms | {resnet_summary['latency_ms']['avg_total_query_latency_ms']:<15.2f} ms |")
    print("=" * 75)

    elapsed = time.time() - start_time
    print(f"\nUnified evaluation completed in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    args = parse_args()
    run_baseline_evaluation(
        gt_csv_path=args.gt_csv,
        id_map_csv_path=args.id_map_csv,
        split=args.split,
        top_k=args.top_k,
        results_dir=args.results_dir,
    )
