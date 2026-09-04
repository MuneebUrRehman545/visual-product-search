"""Human-reviewable ground truth workflow for Visual Product Search (Week 3).

1. Generates/updates evaluation/ground_truth_review.csv with review_status (pending, approved, rejected).
2. Generates visual contact sheets in evaluation/review_sheets/ for human inspection.
3. Exports evaluation/ground_truth.csv ONLY from rows where review_status == 'approved'.
"""

import argparse
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATES = PROJECT_ROOT / "evaluation" / "ground_truth_candidates.csv"
DEFAULT_REVIEW_CSV = PROJECT_ROOT / "evaluation" / "ground_truth_review.csv"
DEFAULT_FINAL_GT = PROJECT_ROOT / "evaluation" / "ground_truth.csv"
DEFAULT_CATALOG_CSV = PROJECT_ROOT / "data" / "splits" / "catalog.csv"
DEFAULT_SHEETS_DIR = PROJECT_ROOT / "evaluation" / "review_sheets"

ALLOWED_STATUSES = {"approved", "rejected", "pending"}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Build and export human-reviewable ground truth.")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_CANDIDATES,
        help="Path to ground_truth_candidates.csv",
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        default=DEFAULT_REVIEW_CSV,
        help="Path to ground_truth_review.csv",
    )
    parser.add_argument(
        "--catalog-csv",
        type=Path,
        default=DEFAULT_CATALOG_CSV,
        help="Path to data/splits/catalog.csv",
    )
    parser.add_argument(
        "--output-gt",
        type=Path,
        default=DEFAULT_FINAL_GT,
        help="Path to output final verified evaluation/ground_truth.csv",
    )
    parser.add_argument(
        "--sheets-dir",
        type=Path,
        default=DEFAULT_SHEETS_DIR,
        help="Directory to save visual contact sheets",
    )
    parser.add_argument(
        "--generate-sheets",
        action="store_true",
        default=True,
        help="Generate visual contact sheets for inspection (default: True)",
    )
    parser.add_argument(
        "--max-sheets",
        type=int,
        default=50,
        help="Maximum contact sheets to render (default: 50 for quick inspection)",
    )
    parser.add_argument(
        "--export-approved",
        action="store_true",
        default=False,
        help="Export approved rows to evaluation/ground_truth.csv",
    )
    return parser.parse_args()


def initialize_review_csv(candidates_path: Path, review_path: Path) -> pd.DataFrame:
    """Create or update review CSV while preserving any existing human reviews."""
    if not candidates_path.exists():
        raise FileNotFoundError(f"Candidate file not found: {candidates_path}")

    df_cand = pd.read_csv(candidates_path)

    existing_reviews: Dict[str, Tuple[str, str]] = {}
    if review_path.exists():
        df_existing = pd.read_csv(review_path)
        for _, row in df_existing.iterrows():
            qid = str(row.get("query_id", "")).strip()
            status = str(row.get("review_status", "pending")).strip().lower()
            notes = str(row.get("review_notes", "")) if pd.notnull(row.get("review_notes")) else ""
            if status in ALLOWED_STATUSES:
                existing_reviews[qid] = (status, notes)

    review_rows = []
    for _, row in df_cand.iterrows():
        qid = str(row["query_id"]).strip()
        existing_status, existing_notes = existing_reviews.get(qid, ("pending", ""))

        review_rows.append(
            {
                "query_id": qid,
                "query_path": str(row["query_path"]).strip(),
                "query_product_id": int(row["product_id"]),
                "relevant_catalog_ids": str(row["relevant_catalog_item_ids"]).strip(),
                "category": str(row.get("category", "")).strip(),
                "article_type": str(row.get("article_type", "")).strip(),
                "product_name": str(row.get("product_name", "")).strip(),
                "split": str(row["split"]).strip(),
                "review_status": existing_status,
                "review_notes": existing_notes,
            }
        )

    df_review = pd.DataFrame(review_rows)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    df_review.to_csv(review_path, index=False)
    return df_review


def render_contact_sheet(
    query_info: Dict[str, Any],
    output_path: Path,
    img_size: Tuple[int, int] = (150, 200),
) -> None:
    """Render a visual contact sheet comparing query image against candidate matches."""
    query_path = PROJECT_ROOT / query_info["query_path"]
    rel_ids = [x.strip() for x in str(query_info["relevant_catalog_ids"]).split(",") if x.strip()]

    # Load images
    query_img = Image.open(query_path).convert("RGB").resize(img_size) if query_path.exists() else Image.new("RGB", img_size, color="gray")

    cat_images: List[Tuple[str, Image.Image]] = []
    for cid in rel_ids[:6]:  # Show up to 6 matches on sheet
        c_path = PROJECT_ROOT / "data" / "images" / f"{cid}.jpg"
        if c_path.exists():
            cat_images.append((cid, Image.open(c_path).convert("RGB").resize(img_size)))
        else:
            cat_images.append((cid, Image.new("RGB", img_size, color="gray")))

    total_cols = 1 + max(1, len(cat_images))
    sheet_w = total_cols * (img_size[0] + 20) + 20
    sheet_h = img_size[1] + 120

    sheet = Image.new("RGB", (sheet_w, sheet_h), color="#1e1e2e")
    draw = ImageDraw.Draw(sheet)

    # Header
    title = f"Query: {query_info['query_id']} | Product: {query_info['product_name'][:30]} | Split: {query_info['split']} | Status: {query_info['review_status']}"
    draw.text((20, 15), title, fill="#cdd6f4")

    # Draw Query Image
    x = 20
    y = 50
    draw.rectangle([x - 2, y - 2, x + img_size[0] + 2, y + img_size[1] + 2], outline="#f38ba8", width=2)
    sheet.paste(query_img, (x, y))
    draw.text((x, y + img_size[1] + 5), f"QUERY: {query_info['query_path'].split('/')[-1]}", fill="#f38ba8")
    draw.text((x, y + img_size[1] + 20), f"PID: {query_info['query_product_id']}", fill="#a6adc8")

    # Draw Catalog Matches
    for idx, (cid, c_img) in enumerate(cat_images):
        cx = x + (idx + 1) * (img_size[0] + 20)
        draw.rectangle([cx - 2, y - 2, cx + img_size[0] + 2, y + img_size[1] + 2], outline="#a6e3a1", width=2)
        sheet.paste(c_img, (cx, y))
        draw.text((cx, y + img_size[1] + 5), f"MATCH #{idx+1}: {cid}.jpg", fill="#a6e3a1")
        draw.text((cx, y + img_size[1] + 20), f"Catalog ID: {cid}", fill="#a6adc8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=90)


def generate_all_contact_sheets(
    df_review: pd.DataFrame,
    sheets_dir: Path,
    max_sheets: int = 50,
) -> int:
    """Generate visual contact sheets for inspection."""
    sheets_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    records = df_review.to_dict(orient="records")
    for rec in records[:max_sheets]:
        qid = rec["query_id"]
        out_p = sheets_dir / f"sheet_{qid}.jpg"
        render_contact_sheet(rec, out_p)
        count += 1
    return count


def export_approved_ground_truth(
    review_path: Path,
    catalog_csv_path: Path,
    output_gt_path: Path,
) -> Tuple[int, int, str]:
    """Export ONLY approved rows to evaluation/ground_truth.csv with full verification."""
    if not review_path.exists():
        raise FileNotFoundError(f"Review CSV not found: {review_path}")
    if not catalog_csv_path.exists():
        raise FileNotFoundError(f"Catalog CSV not found: {catalog_csv_path}")

    df_review = pd.read_csv(review_path)
    df_catalog = pd.read_csv(catalog_csv_path)
    catalog_ids = set(df_catalog["image_id"].astype(int))

    approved_rows = df_review[df_review["review_status"] == "approved"]
    pending_rows = df_review[df_review["review_status"] == "pending"]
    rejected_rows = df_review[df_review["review_status"] == "rejected"]

    approved_count = len(approved_rows)
    pending_count = len(pending_rows)
    rejected_count = len(rejected_rows)

    if approved_count == 0:
        msg = (
            f"[PENDING REVIEW] 0 queries are currently marked 'approved' in {review_path.name} "
            f"({pending_count} pending, {rejected_count} rejected). Evaluation is waiting for manual review."
        )
        return approved_count, pending_count, msg

    # Verification checks for approved rows
    verified_gt_records = []
    for _, row in approved_rows.iterrows():
        qid = str(row["query_id"]).strip()
        q_path = str(row["query_path"]).strip()
        rel_ids_raw = str(row["relevant_catalog_ids"]).strip()
        rel_ids = [int(x) for x in rel_ids_raw.split(",") if x.strip()]

        # Check 1: Must have >= 1 relevant ID
        if len(rel_ids) == 0:
            raise ValueError(f"Approved query {qid} has 0 relevant catalog IDs.")

        # Check 2: Query itself must not be in relevant catalog IDs
        q_img_id = int(Path(q_path).stem) if Path(q_path).stem.isdigit() else None
        if q_img_id and q_img_id in rel_ids:
            raise ValueError(f"Query {qid} ({q_img_id}) leaked into its own relevant catalog IDs!")

        # Check 3: All relevant IDs must exist in catalog.csv
        missing_in_catalog = [cid for cid in rel_ids if cid not in catalog_ids]
        if missing_in_catalog:
            raise ValueError(f"Approved query {qid} references IDs not in catalog: {missing_in_catalog}")

        verified_gt_records.append(
            {
                "query_id": qid,
                "query_path": q_path,
                "product_id": row["query_product_id"],
                "relevant_catalog_ids": rel_ids_raw,
                "category": row.get("category", ""),
                "split": row["split"],
                "review_status": "approved",
                "review_notes": row.get("review_notes", ""),
            }
        )

    df_gt = pd.DataFrame(verified_gt_records)
    output_gt_path.parent.mkdir(parents=True, exist_ok=True)
    df_gt.to_csv(output_gt_path, index=False)
    rel_out = Path(output_gt_path).resolve().relative_to(PROJECT_ROOT.resolve())
    msg = f"[SUCCESS] Exported {approved_count} approved ground-truth queries to {rel_out}."
    return approved_count, pending_count, msg


def main() -> None:
    """Execute ground truth review preparation and verification."""
    args = parse_args()
    print("=" * 70)
    print(" " * 16 + "GROUND TRUTH REVIEW WORKFLOW")
    print("=" * 70)

    # 1. Initialize / update ground_truth_review.csv
    df_review = initialize_review_csv(args.candidates, args.review_csv)
    total_review_rows = len(df_review)
    status_counts = df_review["review_status"].value_counts().to_dict()

    print(f"Generated/Updated Review CSV: {args.review_csv.relative_to(PROJECT_ROOT)}")
    print(f"Total Review Rows:            {total_review_rows}")
    print(f"Status Breakdown:             {status_counts}")

    # 2. Generate visual contact sheets
    if args.generate_sheets:
        sheets_rendered = generate_all_contact_sheets(df_review, args.sheets_dir, max_sheets=args.max_sheets)
        print(f"\nGenerated {sheets_rendered} visual contact sheets in: {args.sheets_dir.relative_to(PROJECT_ROOT)}")
        print(f"  Sample sheet: {args.sheets_dir.relative_to(PROJECT_ROOT)}/sheet_val_q001.jpg")

    # 3. Export approved ground truth if requested or check status
    approved_count, pending_count, msg = export_approved_ground_truth(
        args.review_csv, args.catalog_csv, args.output_gt
    )
    print(f"\nExport / Verification Check:")
    print(f"  {msg}")
    print("=" * 70)


if __name__ == "__main__":
    main()
