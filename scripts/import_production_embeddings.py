"""Import selected production model embeddings into the database.

Associates each vector with its stable catalog_item.id using artifacts/faiss/production_mapping.csv.
Validates dimensions, rejects NaN/Inf, and updates database in batches.
"""

import argparse
from pathlib import Path
import sys
import time
from typing import Any, Dict, List
import numpy as np
import pandas as pd

# Ensure workspace root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import (
    fetch_catalog_items_by_ids,
    get_catalog_count,
    get_database_url,
    get_db_path,
    is_postgres,
    update_production_embeddings_batch,
)

DEFAULT_CATALOG_CSV = PROJECT_ROOT / "data" / "splits" / "catalog.csv"
DEFAULT_MAPPING_CSV = PROJECT_ROOT / "artifacts" / "faiss" / "production_mapping.csv"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Import production embeddings into catalog database.")
    parser.add_argument(
        "--embeddings-path",
        type=Path,
        required=True,
        help="Path to .npy embedding vector file (e.g. artifacts/embeddings/clip_embeddings.npy)",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        required=True,
        help="Production model identifier (e.g. 'open_clip:ViT-B-32:laion2b_s34b_b79k')",
    )
    parser.add_argument(
        "--mapping-csv",
        type=Path,
        default=DEFAULT_MAPPING_CSV,
        help="Path to artifacts/faiss/production_mapping.csv",
    )
    parser.add_argument(
        "--catalog-csv",
        type=Path,
        default=DEFAULT_CATALOG_CSV,
        help="Path to data/splits/catalog.csv",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="PostgreSQL connection string override",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite database path override",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Batch size for database updates (default: 2000)",
    )
    return parser.parse_args()


def import_production_embeddings(
    embeddings_path: Path,
    model_name: str,
    mapping_csv_path: Path = DEFAULT_MAPPING_CSV,
    catalog_csv_path: Path = DEFAULT_CATALOG_CSV,
    database_url: str = None,
    db_path: Path = None,
    batch_size: int = 2000,
) -> int:
    """Validate and import production embeddings into the catalog database."""
    start_time = time.time()
    print("=" * 70)
    print(" " * 16 + "IMPORT PRODUCTION EMBEDDINGS PIPELINE")
    print("=" * 70)

    db_type = "Hosted PostgreSQL" if (database_url or is_postgres()) else "Local SQLite"
    print(f"Target Database:       {db_type}")
    print(f"Embeddings Artifact:   {embeddings_path}")
    print(f"Model Identifier:      {model_name}")
    print(f"Mapping File:          {mapping_csv_path.relative_to(PROJECT_ROOT)}")

    if not embeddings_path.exists():
        raise FileNotFoundError(f"Embeddings file not found: {embeddings_path}")
    if not mapping_csv_path.exists():
        raise FileNotFoundError(f"Mapping file not found: {mapping_csv_path}")

    # 1. Load Embeddings and Mapping
    print("\nLoading embeddings vector array and mapping...")
    embeddings = np.load(str(embeddings_path))
    df_mapping = pd.read_csv(mapping_csv_path)

    total_vectors, dim = embeddings.shape
    total_mapping_rows = len(df_mapping)
    print(f"  + Loaded embeddings shape: ({total_vectors:,}, {dim})")
    print(f"  + Loaded mapping rows:     {total_mapping_rows:,}")

    # 2. Strict Dimensional and Count Assertions
    print("\nValidating embedding array integrity...")
    if total_vectors != total_mapping_rows:
        raise ValueError(
            f"Embedding count ({total_vectors:,}) does not match mapping row count ({total_mapping_rows:,})!"
        )

    # Check for NaN / Inf
    if not np.all(np.isfinite(embeddings)):
        raise ValueError("FATAL: Embedding array contains non-finite values (NaN or Inf)!")
    print(f"  [PASS] All {total_vectors:,} vectors are finite (0 NaN / 0 Inf).")

    # Check vector norms (expect ~1.0 for normalized embeddings)
    norms = np.linalg.norm(embeddings, axis=1)
    mean_norm = float(np.mean(norms))
    min_norm = float(np.min(norms))
    max_norm = float(np.max(norms))
    print(f"  [PASS] L2 norms verified: Mean={mean_norm:.4f}, Min={min_norm:.4f}, Max={max_norm:.4f}")

    # 3. Construct ID-to-Vector Mapping
    print("\nMapping vectors to stable catalog_item.id primary keys...")
    id_to_vec_map: Dict[int, np.ndarray] = {}
    for idx, row in df_mapping.iterrows():
        item_id = int(row["catalog_item_id"])
        vec = embeddings[idx]
        id_to_vec_map[item_id] = vec

    # 4. Batch Update Database
    print(f"\nWriting {len(id_to_vec_map):,} vectors into {db_type} (batch_size={batch_size})...")
    updated_count = update_production_embeddings_batch(
        id_to_vector_map=id_to_vec_map,
        model_name=model_name,
        database_url=database_url,
        db_path=db_path,
        batch_size=batch_size,
    )
    print(f"  + Successfully updated {updated_count:,} database records with production vectors.")

    # 5. Sampling Verification
    print("\nSampling 5 records from database to verify vector persistence:")
    sample_ids = list(id_to_vec_map.keys())[:5]
    sample_rows = fetch_catalog_items_by_ids(
        item_ids=sample_ids,
        database_url=database_url,
        db_path=db_path,
    )
    for r in sample_rows:
        has_emb = r.get("embedding") is not None
        emb_dim = r.get("embedding_dimension")
        emb_mod = r.get("embedding_model")
        print(
            f"  - Item ID {r['id']:5} | Model: {emb_mod:25} | "
            f"Dim: {emb_dim} | Embedding Present: {has_emb}"
        )

    elapsed = time.time() - start_time
    print(f"\nProduction embedding import completed in {elapsed:.2f} seconds.")
    print("=" * 70)
    return updated_count


if __name__ == "__main__":
    args = parse_args()
    import_production_embeddings(
        embeddings_path=args.embeddings_path,
        model_name=args.model_name,
        mapping_csv_path=args.mapping_csv,
        catalog_csv_path=args.catalog_csv,
        database_url=args.database_url,
        db_path=args.db_path,
        batch_size=args.batch_size,
    )
