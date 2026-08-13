"""Script to evaluate and compare CLIP vs ResNet-50 visual search models on evaluation dataset."""

import csv
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Dict, List, Set

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_all_products
from app.services.clip_search_service import CLIPSearchService
from app.services.resnet_search_service import ResNetSearchService

EVALUATION_DIR = PROJECT_ROOT / "data" / "evaluation"
QUERIES_DIR = EVALUATION_DIR / "queries"
GROUND_TRUTH_FILE = EVALUATION_DIR / "ground_truth.csv"
PER_QUERY_RESULTS_FILE = EVALUATION_DIR / "per_query_results.csv"
COMPARISON_RESULTS_FILE = EVALUATION_DIR / "comparison_results.json"


def load_valid_db_product_ids() -> Set[int]:
    """Fetch set of valid product IDs from SQLite."""
    try:
        products = fetch_all_products()
        return {prod["id"] for prod in products}
    except Exception as e:
        print(f"Error fetching product IDs from SQLite: {e}", file=sys.stderr)
        sys.exit(1)


def parse_ground_truth(db_product_ids: Set[int]) -> List[Dict[str, Any]]:
    """Parse ground truth CSV and validate query files and product IDs."""
    if not GROUND_TRUTH_FILE.exists():
        print(f"Error: Ground truth file '{GROUND_TRUTH_FILE}' not found.", file=sys.stderr)
        sys.exit(1)

    queries: List[Dict[str, Any]] = []
    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader, start=2):
            filename = row["query_filename"].strip()
            variation = row.get("variation", "unknown").strip()
            raw_ids = row.get("relevant_product_ids", "").strip()

            if not raw_ids:
                print(f"Warning: Line {row_idx}: Empty relevant_product_ids for {filename}. Skipping.", file=sys.stderr)
                continue

            try:
                rel_ids = [int(pid.strip()) for pid in raw_ids.split("|") if pid.strip()]
            except ValueError:
                print(f"Warning: Line {row_idx}: Invalid integer in relevant_product_ids '{raw_ids}'. Skipping.", file=sys.stderr)
                continue

            # Validate query file exists
            query_path = QUERIES_DIR / filename
            if not query_path.exists():
                print(f"Warning: Query image file '{query_path}' does not exist. Skipping.", file=sys.stderr)
                continue

            # Validate DB product IDs exist
            missing_ids = [pid for pid in rel_ids if pid not in db_product_ids]
            if missing_ids:
                print(
                    f"Warning: Line {row_idx}: Product IDs {missing_ids} not found in SQLite database. Skipping.",
                    file=sys.stderr,
                )
                continue

            queries.append(
                {
                    "filename": filename,
                    "filepath": query_path,
                    "relevant_ids": set(rel_ids),
                    "variation": variation,
                }
            )

    return queries


def calculate_precision_recall(retrieved_ids: List[int], relevant_ids: Set[int], k: int) -> tuple[float, float]:
    """Calculate Precision@k and Recall@k."""
    top_k_retrieved = retrieved_ids[:k]
    num_relevant_retrieved = sum(1 for pid in top_k_retrieved if pid in relevant_ids)
    precision = num_relevant_retrieved / k if k > 0 else 0.0
    recall = num_relevant_retrieved / len(relevant_ids) if len(relevant_ids) > 0 else 0.0
    return precision, recall


def compute_aggregate_metrics(metrics_list: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute mean precision/recall and avg/median latency for a model run."""
    if not metrics_list:
        return {
            "precision_at_1": 0.0,
            "precision_at_5": 0.0,
            "precision_at_10": 0.0,
            "recall_at_1": 0.0,
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "avg_latency_ms": 0.0,
            "median_latency_ms": 0.0,
        }

    latencies = [m["latency_ms"] for m in metrics_list]
    return {
        "precision_at_1": round(statistics.mean(m["p1"] for m in metrics_list), 4),
        "precision_at_5": round(statistics.mean(m["p5"] for m in metrics_list), 4),
        "precision_at_10": round(statistics.mean(m["p10"] for m in metrics_list), 4),
        "recall_at_1": round(statistics.mean(m["r1"] for m in metrics_list), 4),
        "recall_at_5": round(statistics.mean(m["r5"] for m in metrics_list), 4),
        "recall_at_10": round(statistics.mean(m["r10"] for m in metrics_list), 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2),
        "median_latency_ms": round(statistics.median(latencies), 2),
    }


def main() -> None:
    print("Loading SQLite product IDs...")
    db_product_ids = load_valid_db_product_ids()

    print("Parsing and validating ground-truth data...")
    queries = parse_ground_truth(db_product_ids)
    total_valid = len(queries)
    print(f"Total valid evaluation queries: {total_valid}")

    if total_valid == 0:
        print("Error: No valid queries were found to evaluate.", file=sys.stderr)
        sys.exit(1)

    print("\nInitializing CLIP and ResNet-50 search services (excluding loading time from latency)...")
    clip_service = CLIPSearchService()
    resnet_service = ResNetSearchService()

    per_query_records = []
    clip_metrics_all = []
    resnet_metrics_all = []

    variations_map: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    print(f"Evaluating {total_valid} queries...")
    for idx, q in enumerate(queries, start=1):
        filename = q["filename"]
        filepath = q["filepath"]
        rel_ids = q["relevant_ids"]
        variation = q["variation"]

        # Run CLIP search (top_k=10)
        t0 = time.perf_counter()
        clip_res = clip_service.search(filepath, top_k=10)
        clip_latency_ms = (time.perf_counter() - t0) * 1000.0

        clip_ids = [r["product_id"] for r in clip_res]
        cp1, cr1 = calculate_precision_recall(clip_ids, rel_ids, 1)
        cp5, cr5 = calculate_precision_recall(clip_ids, rel_ids, 5)
        cp10, cr10 = calculate_precision_recall(clip_ids, rel_ids, 10)

        clip_m = {
            "p1": cp1, "p5": cp5, "p10": cp10,
            "r1": cr1, "r5": cr5, "r10": cr10,
            "latency_ms": clip_latency_ms,
        }
        clip_metrics_all.append(clip_m)

        # Run ResNet search (top_k=10)
        t0 = time.perf_counter()
        resnet_res = resnet_service.search(filepath, top_k=10)
        resnet_latency_ms = (time.perf_counter() - t0) * 1000.0

        resnet_ids = [r["product_id"] for r in resnet_res]
        rp1, rr1 = calculate_precision_recall(resnet_ids, rel_ids, 1)
        rp5, rr5 = calculate_precision_recall(resnet_ids, rel_ids, 5)
        rp10, rr10 = calculate_precision_recall(resnet_ids, rel_ids, 10)

        resnet_m = {
            "p1": rp1, "p5": rp5, "p10": rp10,
            "r1": rr1, "r5": rr5, "r10": rr10,
            "latency_ms": resnet_latency_ms,
        }
        resnet_metrics_all.append(resnet_m)

        if variation not in variations_map:
            variations_map[variation] = {"clip": [], "resnet50": []}
        variations_map[variation]["clip"].append(clip_m)
        variations_map[variation]["resnet50"].append(resnet_m)

        per_query_records.append(
            {
                "query_filename": filename,
                "variation": variation,
                "relevant_product_ids": "|".join(str(i) for i in sorted(rel_ids)),
                "clip_precision_1": round(cp1, 4),
                "clip_precision_5": round(cp5, 4),
                "clip_precision_10": round(cp10, 4),
                "clip_recall_1": round(cr1, 4),
                "clip_recall_5": round(cr5, 4),
                "clip_recall_10": round(cr10, 4),
                "clip_latency_ms": round(clip_latency_ms, 2),
                "resnet_precision_1": round(rp1, 4),
                "resnet_precision_5": round(rp5, 4),
                "resnet_precision_10": round(rp10, 4),
                "resnet_recall_1": round(rr1, 4),
                "resnet_recall_5": round(rr5, 4),
                "resnet_recall_10": round(rr10, 4),
                "resnet_latency_ms": round(resnet_latency_ms, 2),
            }
        )

    # Save per-query CSV
    fieldnames = list(per_query_records[0].keys())
    with open(PER_QUERY_RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(per_query_records)
    print(f"Saved detailed per-query results to: {PER_QUERY_RESULTS_FILE}")

    # Compute overall & grouped metrics
    overall_clip = compute_aggregate_metrics(clip_metrics_all)
    overall_resnet = compute_aggregate_metrics(resnet_metrics_all)

    by_variation_json = {}
    for var_name, model_dict in sorted(variations_map.items()):
        by_variation_json[var_name] = {
            "clip": compute_aggregate_metrics(model_dict["clip"]),
            "resnet50": compute_aggregate_metrics(model_dict["resnet50"]),
        }

    summary_json = {
        "total_queries_evaluated": total_valid,
        "overall_metrics": {
            "clip": overall_clip,
            "resnet50": overall_resnet,
        },
        "metrics_by_variation": by_variation_json,
    }

    with open(COMPARISON_RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(summary_json, f, indent=2)
    print(f"Saved summary metrics to: {COMPARISON_RESULTS_FILE}")

    # Print comparison table
    print("\n" + "=" * 80)
    print(f"OVERALL EVALUATION SUMMARY (Total Queries: {total_valid})")
    print("=" * 80)
    print(f"{'Metric':<25} {'CLIP (ViT-B-32)':<25} {'ResNet-50':<25}")
    print("-" * 80)
    print(f"{'Precision@1':<25} {overall_clip['precision_at_1']:<25.4f} {overall_resnet['precision_at_1']:<25.4f}")
    print(f"{'Precision@5':<25} {overall_clip['precision_at_5']:<25.4f} {overall_resnet['precision_at_5']:<25.4f}")
    print(f"{'Precision@10':<25} {overall_clip['precision_at_10']:<25.4f} {overall_resnet['precision_at_10']:<25.4f}")
    print(f"{'Recall@1':<25} {overall_clip['recall_at_1']:<25.4f} {overall_resnet['recall_at_1']:<25.4f}")
    print(f"{'Recall@5':<25} {overall_clip['recall_at_5']:<25.4f} {overall_resnet['recall_at_5']:<25.4f}")
    print(f"{'Recall@10':<25} {overall_clip['recall_at_10']:<25.4f} {overall_resnet['recall_at_10']:<25.4f}")
    print(f"{'Avg Latency (ms)':<25} {overall_clip['avg_latency_ms']:<25.2f} {overall_resnet['avg_latency_ms']:<25.2f}")
    print(f"{'Median Latency (ms)':<25} {overall_clip['median_latency_ms']:<25.2f} {overall_resnet['median_latency_ms']:<25.2f}")
    print("=" * 80)

    if by_variation_json:
        print("\n" + "=" * 80)
        print("PER-VARIATION SUMMARY (Precision@5 / Recall@5)")
        print("=" * 80)
        print(f"{'Variation':<25} {'CLIP (P@5 / R@5)':<25} {'ResNet-50 (P@5 / R@5)':<25}")
        print("-" * 80)
        for var_name, var_data in by_variation_json.items():
            clip_p5 = var_data["clip"]["precision_at_5"]
            clip_r5 = var_data["clip"]["recall_at_5"]
            res_p5 = var_data["resnet50"]["precision_at_5"]
            res_r5 = var_data["resnet50"]["recall_at_5"]
            print(
                f"{var_name:<25} "
                f"{clip_p5:.4f} / {clip_r5:.4f}{'':<12} "
                f"{res_p5:.4f} / {res_r5:.4f}"
            )
        print("=" * 80)

    print("\nEvaluation completed successfully.")


if __name__ == "__main__":
    main()
