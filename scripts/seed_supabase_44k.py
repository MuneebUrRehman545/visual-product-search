"""Script to seed the 44,119-item production catalog from SQLite into remote Supabase PostgreSQL."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
import time
from dotenv import load_dotenv
import psycopg2
from psycopg2 import extras

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SQLITE_PATH = PROJECT_ROOT / "data" / "catalog.db"
DEFAULT_BATCH_SIZE = 1000


def seed_supabase_44k(batch_size: int = DEFAULT_BATCH_SIZE) -> None:
    start_time = time.time()
    print("=" * 70)
    print(" " * 15 + "SEED 44K CATALOG TO SUPABASE POSTGRESQL")
    print("=" * 70)

    url = os.getenv("SHARED_DATABASE_URL")
    if not url:
        raise ValueError("SHARED_DATABASE_URL not found in .env!")

    from urllib.parse import urlparse
    parsed = urlparse(url)
    print(f"Target Database Host:  {parsed.hostname}")
    print(f"Target Database User:  {parsed.username}")
    print(f"Source SQLite DB:      {SQLITE_PATH}")

    if not SQLITE_PATH.exists():
        raise FileNotFoundError(f"Local SQLite database not found: {SQLITE_PATH}")

    # 1. Connect to SQLite
    print("\n[1/5] Reading records from local SQLite catalog.db...")
    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    sqlite_cur.execute("SELECT count(*) FROM catalog_items;")
    total_source_rows = sqlite_cur.fetchone()[0]
    print(f"  + Source catalog_items count: {total_source_rows:,} rows")

    if total_source_rows != 44119:
        print(f"  [WARNING] Expected 44,119 rows, found {total_source_rows:,}")

    # Fetch all rows ordered by id
    sqlite_cur.execute("""
        SELECT 
            id, image_id, product_id, external_id, filename, image_url,
            relative_path, category, master_category, sub_category,
            article_type, gender, base_colour, season, year, usage,
            product_display_name, embedding, embedding_dimension,
            embedding_model, created_at, updated_at
        FROM catalog_items
        ORDER BY id ASC;
    """)
    rows = sqlite_cur.fetchall()
    print(f"  + Loaded {len(rows):,} rows into memory.")

    # 2. Connect to remote PostgreSQL
    print("\n[2/5] Connecting to remote Supabase PostgreSQL...")
    pg_conn = psycopg2.connect(url, connect_timeout=30)
    pg_cur = pg_conn.cursor()

    # Check current row count
    pg_cur.execute("SELECT count(*), min(id), max(id) FROM catalog_items;")
    pre_count, pre_min, pre_max = pg_cur.fetchone()
    print(f"  + Current remote status: {pre_count:,} rows (IDs {pre_min}..{pre_max})")

    # 3. Truncate table
    print("\n[3/5] Truncating remote catalog_items table...")
    pg_cur.execute("TRUNCATE TABLE catalog_items RESTART IDENTITY;")
    print("  + Table truncated successfully.")

    # 4. Batch Insert
    print(f"\n[4/5] Inserting {len(rows):,} rows in batches of {batch_size}...")
    insert_sql = """
        INSERT INTO catalog_items (
            id, image_id, product_id, external_id, filename, image_url,
            relative_path, category, master_category, sub_category,
            article_type, gender, base_colour, season, year, usage,
            product_display_name, embedding, embedding_dimension,
            embedding_model, created_at, updated_at
        ) VALUES %s
    """

    now_ts = datetime.now(timezone.utc)
    inserted_count = 0
    batch_tuples = []

    for idx, r in enumerate(rows):
        emb_bytes = bytes(r["embedding"]) if r["embedding"] is not None else None
        emb_binary = psycopg2.Binary(emb_bytes) if emb_bytes else None

        tup = (
            int(r["id"]),
            int(r["image_id"]),
            int(r["product_id"]),
            str(r["external_id"]),
            str(r["filename"]),
            str(r["image_url"]) if r["image_url"] else f"/catalog-images/{r['filename']}",
            str(r["relative_path"]) if r["relative_path"] else f"data/images/{r['filename']}",
            r["category"],
            r["master_category"],
            r["sub_category"],
            r["article_type"],
            r["gender"],
            r["base_colour"],
            r["season"],
            int(r["year"]) if r["year"] is not None and str(r["year"]).isdigit() else None,
            r["usage"],
            r["product_display_name"],
            emb_binary,
            int(r["embedding_dimension"]) if r["embedding_dimension"] is not None else 512,
            r["embedding_model"] or "open_clip:ViT-B-32:laion2b_s34b_b79k",
            r["created_at"] or now_ts,
            r["updated_at"] or now_ts,
        )
        batch_tuples.append(tup)

        if len(batch_tuples) >= batch_size or idx == len(rows) - 1:
            extras.execute_values(pg_cur, insert_sql, batch_tuples, page_size=batch_size)
            inserted_count += len(batch_tuples)
            batch_tuples = []
            if inserted_count % 5000 == 0 or inserted_count == len(rows):
                print(f"  + Uploaded {inserted_count:,} / {len(rows):,} rows...")

    # Update sequence
    print("\n[5/5] Resetting PostgreSQL primary key sequence...")
    pg_cur.execute("SELECT setval(pg_get_serial_sequence('catalog_items', 'id'), (SELECT max(id) FROM catalog_items), true);")
    seq_val = pg_cur.fetchone()[0]
    print(f"  + Sequence 'catalog_items_id_seq' set to: {seq_val}")

    # Commit transaction
    print("  + Committing transaction to Supabase...")
    pg_conn.commit()

    # 5. Verification Assertions
    print("\n" + "=" * 70)
    print(" " * 22 + "VERIFICATION ASSERTIONS")
    print("=" * 70)

    pg_cur.execute("SELECT count(*), min(id), max(id) FROM catalog_items;")
    post_count, post_min, post_max = pg_cur.fetchone()
    print(f"  - Total Row Count:      {post_count:,} (Expected: {total_source_rows:,})")
    print(f"  - Primary Key Range:    min={post_min}, max={post_max} (Expected: 1..{total_source_rows})")

    assert post_count == total_source_rows, f"Count mismatch: {post_count} != {total_source_rows}"
    assert post_min == 1, f"Min ID mismatch: {post_min} != 1"
    assert post_max == total_source_rows, f"Max ID mismatch: {post_max} != {total_source_rows}"

    pg_cur.execute("SELECT count(*) FROM catalog_items WHERE embedding IS NOT NULL;")
    emb_count = pg_cur.fetchone()[0]
    print(f"  - Populated Embeddings: {emb_count:,} (Expected: {total_source_rows:,})")
    assert emb_count == total_source_rows, f"Embedding count mismatch: {emb_count} != {total_source_rows}"

    # Spot checks
    print("\nSampling 3 spot-check records from remote PostgreSQL:")
    for check_id in [1, 2301, 44119]:
        pg_cur.execute("""
            SELECT id, filename, product_display_name, category, length(embedding), embedding_model
            FROM catalog_items WHERE id = %s;
        """, (check_id,))
        row = pg_cur.fetchone()
        print(f"  - ID {row[0]:5} | File: {row[1]:10} | Cat: {row[3]:15} | Emb Bytes: {row[4]} | Title: {row[2][:35]}")

    pg_conn.close()
    sqlite_conn.close()

    elapsed = time.time() - start_time
    print(f"\nMigration completed successfully in {elapsed:.2f} seconds!")
    print("=" * 70)


if __name__ == "__main__":
    seed_supabase_44k()
