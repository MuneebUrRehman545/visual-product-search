"""Generate full CLIP embeddings and build Database-ID-aware FAISS index for Week 3.

Inputs:
  - data/splits/catalog.csv (44,119 searchable items)
  - data/manifests/catalog_id_map.csv (stable catalog_item_id mappings)

Outputs:
  - artifacts/embeddings/clip_embeddings.npy
  - artifacts/embeddings/clip_catalog_ids.npy
  - artifacts/faiss/clip.index
  - artifacts/faiss/clip_mapping.csv
  - artifacts/embeddings/clip_fingerprint.json
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import faiss
import numpy as np
import open_clip
import pandas as pd
from PIL import Image
import torch

# Ensure unbuffered stdout
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# Ensure workspace root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import fetch_catalog_items_by_ids

DEFAULT_CATALOG_CSV = PROJECT_ROOT / "data" / "splits" / "catalog.csv"
DEFAULT_ID_MAP_CSV = PROJECT_ROOT / "data" / "manifests" / "catalog_id_map.csv"

EMBEDDINGS_DIR = PROJECT_ROOT / "artifacts" / "embeddings"
FAISS_DIR = PROJECT_ROOT / "artifacts" / "faiss"

OUTPUT_EMBEDDINGS = EMBEDDINGS_DIR / "clip_embeddings.npy"
OUTPUT_CATALOG_IDS = EMBEDDINGS_DIR / "clip_catalog_ids.npy"
OUTPUT_FINGERPRINT = EMBEDDINGS_DIR / "clip_fingerprint.json"
OUTPUT_FAISS_INDEX = FAISS_DIR / "clip.index"
OUTPUT_CLIP_MAPPING = FAISS_DIR / "clip_mapping.csv"

MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"
EMBEDDING_DIMENSION = 512


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate full CLIP embeddings and FAISS index.")
    parser.add_argument(
        "--catalog-csv",
        type=Path,
        default=DEFAULT_CATALOG_CSV,
        help="Path to data/splits/catalog.csv",
    )
    parser.add_argument(
        "--id-map-csv",
        type=Path,
        default=DEFAULT_ID_MAP_CSV,
        help="Path to data/manifests/catalog_id_map.csv",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="Inference batch size (default: 256)",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=2000,
        help="Save intermediate checkpoint every N items (default: 2000)",
    )
    parser.add_argument(
        "--force-recompute",
        action="store_true",
        default=False,
        help="Force recomputation of embeddings even if valid checkpoint exists",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for verification sampling (default: 42)",
    )
    return parser.parse_args()


def compute_dataset_fingerprint(catalog_csv_path: Path, id_map_csv_path: Path) -> str:
    """Compute a deterministic SHA256 signature for the input catalog and ID map."""
    hasher = hashlib.sha256()
    with open(catalog_csv_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    with open(id_map_csv_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    hasher.update(f"{MODEL_NAME}:{PRETRAINED}:{EMBEDDING_DIMENSION}".encode("utf-8"))
    return hasher.hexdigest()


def load_single_image(rec: Dict[str, Any], preprocess: Any) -> Tuple[torch.Tensor, int, int]:
    """Load and preprocess a single image."""
    cat_id = int(rec["catalog_item_id"])
    img_id = int(rec["image_id"])
    rel_path = rec["relative_path"]
    full_path = PROJECT_ROOT / rel_path

    try:
        with Image.open(full_path) as img:
            tensor = preprocess(img.convert("RGB"))
            return tensor, cat_id, img_id
    except Exception:
        return torch.zeros((3, 224, 224), dtype=torch.float32), cat_id, img_id


def generate_clip_embeddings(
    catalog_csv_path: Path,
    id_map_csv_path: Path,
    batch_size: int = 256,
    checkpoint_every: int = 2000,
    force_recompute: bool = False,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, faiss.IndexIDMap2]:
    """Generate normalized CLIP embeddings and build FAISS IndexIDMap2."""
    start_time = time.time()
    print("=" * 70, flush=True)
    print(" " * 14 + "CLIP EMBEDDING & FAISS INDEX BUILDER", flush=True)
    print("=" * 70, flush=True)

    num_cpus = os.cpu_count() or 4
    torch.set_num_threads(num_cpus)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print(f"Execution Device:         {device} (Threads: {num_cpus})", flush=True)
    print(f"Model Architecture:       {MODEL_NAME}", flush=True)
    print(f"Pretrained Weights:       {PRETRAINED}", flush=True)
    print(f"Embedding Dimension:      {EMBEDDING_DIMENSION}", flush=True)
    print(f"Batch Size:               {batch_size}", flush=True)

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    FAISS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load catalog & ID map
    df_id_map = pd.read_csv(id_map_csv_path)
    total_items = len(df_id_map)
    print(f"\nLoaded {total_items:,} catalog records for embedding extraction.", flush=True)

    # 2. Check fingerprint & checkpoint resume
    current_fp = compute_dataset_fingerprint(catalog_csv_path, id_map_csv_path)
    ckpt_emb_path = EMBEDDINGS_DIR / "clip_embeddings_checkpoint.npy"
    ckpt_ids_path = EMBEDDINGS_DIR / "clip_catalog_ids_checkpoint.npy"
    ckpt_fp_path = EMBEDDINGS_DIR / "clip_checkpoint_fingerprint.json"

    resume_idx = 0
    all_embeddings_list: List[np.ndarray] = []
    all_catalog_ids_list: List[int] = []

    if not force_recompute and OUTPUT_EMBEDDINGS.exists() and OUTPUT_CATALOG_IDS.exists() and OUTPUT_FINGERPRINT.exists():
        with open(OUTPUT_FINGERPRINT, "r", encoding="utf-8") as f:
            fp_data = json.load(f)
        if fp_data.get("fingerprint") == current_fp:
            print(f"Found completed valid CLIP embeddings ({OUTPUT_EMBEDDINGS.name}). Loading...", flush=True)
            final_embeddings = np.load(str(OUTPUT_EMBEDDINGS))
            final_catalog_ids = np.load(str(OUTPUT_CATALOG_IDS))
            if len(final_embeddings) == total_items and len(final_catalog_ids) == total_items:
                print(f"  + Successfully loaded {len(final_embeddings):,} cached embeddings.", flush=True)
                return final_embeddings, final_catalog_ids, build_and_save_faiss_index(final_embeddings, final_catalog_ids, df_id_map, seed)

    if not force_recompute and ckpt_emb_path.exists() and ckpt_ids_path.exists() and ckpt_fp_path.exists():
        with open(ckpt_fp_path, "r", encoding="utf-8") as f:
            ckpt_fp_data = json.load(f)
        if ckpt_fp_data.get("fingerprint") == current_fp:
            ckpt_embs = np.load(str(ckpt_emb_path))
            ckpt_ids = np.load(str(ckpt_ids_path))
            resume_idx = len(ckpt_embs)
            print(f"Resuming from verified checkpoint: {resume_idx:,}/{total_items:,} items completed.", flush=True)
            all_embeddings_list.append(ckpt_embs)
            all_catalog_ids_list.extend(ckpt_ids.tolist())

    # 3. Load OpenCLIP model & preprocess
    print(f"\nLoading OpenCLIP {MODEL_NAME} ({PRETRAINED}) onto {device}...", flush=True)
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
    model = model.to(device)
    model.eval()

    # 4. Batched inference with parallel image loading
    all_records = df_id_map.to_dict(orient="records")
    remaining_records = all_records[resume_idx:]
    print(f"\nExtracting CLIP embeddings for {len(remaining_records):,} remaining images...", flush=True)

    processed_count = resume_idx
    last_ckpt_count = resume_idx
    batch_start_time = time.time()

    with ThreadPoolExecutor(max_workers=8) as pool:
        for i in range(0, len(remaining_records), batch_size):
            chunk_records = remaining_records[i : i + batch_size]
            results = list(pool.map(lambda r: load_single_image(r, preprocess), chunk_records))

            batch_tensors = torch.stack([r[0] for r in results]).to(device)
            batch_cat_ids = [r[1] for r in results]

            with torch.inference_mode():
                features = model.encode_image(batch_tensors)
                features = features / features.norm(dim=-1, keepdim=True)
                batch_embs = features.cpu().numpy().astype(np.float32)

            all_embeddings_list.append(batch_embs)
            all_catalog_ids_list.extend(batch_cat_ids)
            processed_count += len(batch_cat_ids)

            # Progress output
            rate = (processed_count - resume_idx) / max(0.1, (time.time() - batch_start_time))
            remaining_items = total_items - processed_count
            eta_seconds = remaining_items / max(0.1, rate)
            print(
                f"  [{processed_count:5,}/{total_items:5,}] "
                f"({processed_count/total_items*100:5.1f}%) | "
                f"Speed: {rate:5.1f} img/s | ETA: {eta_seconds/60:4.1f} min",
                flush=True,
            )

            # Periodic Checkpoint
            if processed_count - last_ckpt_count >= checkpoint_every or processed_count == total_items:
                temp_embs = np.concatenate(all_embeddings_list, axis=0)
                temp_ids = np.array(all_catalog_ids_list, dtype=np.int64)
                np.save(str(ckpt_emb_path), temp_embs)
                np.save(str(ckpt_ids_path), temp_ids)
                with open(ckpt_fp_path, "w", encoding="utf-8") as f:
                    json.dump({"fingerprint": current_fp, "count": processed_count}, f, indent=2)
                last_ckpt_count = processed_count

    # 5. Final Concatenation & Validation
    final_embeddings = np.concatenate(all_embeddings_list, axis=0)
    final_catalog_ids = np.array(all_catalog_ids_list, dtype=np.int64)

    assert len(final_embeddings) == total_items, f"Embedding count mismatch: {len(final_embeddings)} != {total_items}"
    assert len(final_catalog_ids) == total_items, f"Catalog ID count mismatch: {len(final_catalog_ids)} != {total_items}"
    assert np.all(np.isfinite(final_embeddings)), "FATAL: Embedding array contains NaN or Inf!"

    # 6. Save final artifacts
    np.save(str(OUTPUT_EMBEDDINGS), final_embeddings)
    np.save(str(OUTPUT_CATALOG_IDS), final_catalog_ids)

    fingerprint_metadata = {
        "model_name": MODEL_NAME,
        "pretrained": PRETRAINED,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "normalization": "L2",
        "total_catalog_items": total_items,
        "fingerprint": current_fp,
        "device_used": str(device),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_FINGERPRINT, "w", encoding="utf-8") as f:
        json.dump(fingerprint_metadata, f, indent=2)

    # Clean up checkpoint files
    if ckpt_emb_path.exists():
        ckpt_emb_path.unlink()
    if ckpt_ids_path.exists():
        ckpt_ids_path.unlink()
    if ckpt_fp_path.exists():
        ckpt_fp_path.unlink()

    print(f"\nSaved final embeddings:", flush=True)
    print(f"  + Vectors:     {OUTPUT_EMBEDDINGS.relative_to(PROJECT_ROOT)} (shape: {final_embeddings.shape})", flush=True)
    print(f"  + Catalog IDs: {OUTPUT_CATALOG_IDS.relative_to(PROJECT_ROOT)} (count: {len(final_catalog_ids):,})", flush=True)
    print(f"  + Fingerprint: {OUTPUT_FINGERPRINT.relative_to(PROJECT_ROOT)}", flush=True)

    # 7. Build FAISS Index and Mapping
    faiss_index = build_and_save_faiss_index(final_embeddings, final_catalog_ids, df_id_map, seed)

    total_elapsed = time.time() - start_time
    print(f"\nCLIP embeddings & FAISS index completed in {total_elapsed:.2f} seconds.", flush=True)
    print("=" * 70, flush=True)
    return final_embeddings, final_catalog_ids, faiss_index


def build_and_save_faiss_index(
    embeddings: np.ndarray,
    catalog_ids: np.ndarray,
    df_id_map: pd.DataFrame,
    seed: int = 42,
) -> faiss.IndexIDMap2:
    """Construct FAISS IndexIDMap2(IndexFlatIP), save to disk, and verify."""
    print("\nConstructing FAISS IndexIDMap2(IndexFlatIP)...", flush=True)
    dim = embeddings.shape[1]

    # Create inner product flat index
    flat_index = faiss.IndexFlatIP(dim)
    # Wrap in IndexIDMap2 for explicit ID mapping
    id_index = faiss.IndexIDMap2(flat_index)

    # Ensure contiguous float32 and int64 IDs
    vectors_contiguous = np.ascontiguousarray(embeddings.astype(np.float32))
    ids_contiguous = np.ascontiguousarray(catalog_ids.astype(np.int64))

    # Add with explicit catalog_item.id primary keys
    id_index.add_with_ids(vectors_contiguous, ids_contiguous)
    print(f"  + FAISS index populated with {id_index.ntotal:,} vectors.", flush=True)

    # Save index to disk
    OUTPUT_FAISS_INDEX.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(id_index, str(OUTPUT_FAISS_INDEX))
    print(f"  + Wrote FAISS index to: {OUTPUT_FAISS_INDEX.relative_to(PROJECT_ROOT)}", flush=True)

    # Write clip_mapping.csv
    mapping_records = []
    for idx, row in df_id_map.iterrows():
        mapping_records.append(
            {
                "faiss_id": int(row["catalog_item_id"]),
                "catalog_item_id": int(row["catalog_item_id"]),
                "image_id": int(row["image_id"]),
                "product_id": int(row["product_id"]),
                "filename": row["filename"],
                "image_url": row.get("image_url", f"/catalog-images/{row['filename']}"),
            }
        )
    df_clip_mapping = pd.DataFrame(mapping_records)
    df_clip_mapping.to_csv(OUTPUT_CLIP_MAPPING, index=False)
    print(f"  + Wrote {len(df_clip_mapping):,} rows to: {OUTPUT_CLIP_MAPPING.relative_to(PROJECT_ROOT)}", flush=True)

    # 8. HARD ASSERTIONS
    print("\nRunning Full Verification & Assertions...", flush=True)

    # Assertion 1: Counts match
    total_expected = len(df_id_map)
    assert len(embeddings) == total_expected, "Embedding count mismatch!"
    assert len(catalog_ids) == total_expected, "Catalog ID count mismatch!"
    assert id_index.ntotal == total_expected, "FAISS ntotal mismatch!"
    assert len(df_clip_mapping) == total_expected, "CLIP mapping rows mismatch!"
    print(f"  [PASS] Counts match exactly ({id_index.ntotal:,} == {total_expected:,}).", flush=True)

    # Assertion 2: Exact ID set match
    set_catalog_ids = set(catalog_ids)
    set_expected_ids = set(df_id_map["catalog_item_id"].astype(int))
    assert set_catalog_ids == set_expected_ids, "CLIP catalog IDs set mismatch with catalog_id_map!"
    print(f"  [PASS] 100% ID alignment between CLIP vectors and catalog_id_map.csv.", flush=True)

    # Assertion 3: Random Sample of 10 FAISS IDs -> Database metadata verification
    random.seed(seed)
    sample_faiss_ids = [int(x) for x in random.sample(list(catalog_ids), k=10)]
    db_items = fetch_catalog_items_by_ids(sample_faiss_ids)
    db_items_map = {r["id"]: r for r in db_items}

    print("\nVerifying Random Sample of 10 FAISS IDs against Database:", flush=True)
    for fid in sample_faiss_ids:
        assert fid in db_items_map, f"FAISS ID {fid} missing in database!"
        db_rec = db_items_map[fid]
        map_rec = df_clip_mapping[df_clip_mapping["faiss_id"] == fid].iloc[0]

        assert db_rec["filename"] == map_rec["filename"], "Filename mismatch!"
        assert (PROJECT_ROOT / "data" / "images" / db_rec["filename"]).exists(), "Image file missing!"
        print(
            f"  - FAISS ID {fid:5} -> DB Item ID: {db_rec['id']:5} | "
            f"Image ID: {db_rec['image_id']:5} | File: {db_rec['filename']:10} | "
            f"Title: {str(db_rec.get('product_display_name', ''))[:30]}",
            flush=True,
        )

    # Assertion 4: Query Search Verification Test
    print("\nExecuting Test Search Query Verification...", flush=True)
    test_query_vec = vectors_contiguous[0:1]
    scores, retrieved_ids = id_index.search(test_query_vec, k=5)
    top_id = int(retrieved_ids[0][0])
    top_score = float(scores[0][0])

    top_db_items = fetch_catalog_items_by_ids([int(x) for x in retrieved_ids[0]])
    print(f"  - Querying Vector ID {ids_contiguous[0]}: Top 1 Returned ID={top_id} (Score={top_score:.4f})", flush=True)
    assert top_id == ids_contiguous[0], "Self-search top result mismatch!"
    assert abs(top_score - 1.0) < 1e-4, f"Normalized cosine score should be ~1.0, got {top_score}"
    assert len(top_db_items) == 5, "Database retrieval count mismatch for search query!"
    print(f"  [PASS] Search retrieval test verified with perfect self-similarity (score={top_score:.4f}).", flush=True)

    return id_index


if __name__ == "__main__":
    args = parse_args()
    generate_clip_embeddings(
        catalog_csv_path=args.catalog_csv,
        id_map_csv_path=args.id_map_csv,
        batch_size=args.batch_size,
        checkpoint_every=args.checkpoint_every,
        force_recompute=args.force_recompute,
        seed=args.seed,
    )
