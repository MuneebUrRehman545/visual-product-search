"""Production Database Service supporting Hosted PostgreSQL (Supabase / Neon) and Local SQLite.

Provides a unified repository interface for managing searchable catalog items,
metadata, deployable image references, and vector embeddings.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Tuple, Union
from dotenv import load_dotenv
import numpy as np

# Load .env once from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Optional PostgreSQL support
try:
    import psycopg2
    from psycopg2 import extras
    import psycopg2.pool
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

try:
    import pgvector.psycopg2
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

logger = logging.getLogger("visual_search.database")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "catalog.db"

# PostgreSQL connection pool (singleton for app lifecycle)
_pg_pool: Optional[Any] = None


def get_database_url() -> Optional[str]:
    """Retrieve catalog database URL with unambiguous integration precedence.

    Precedence:
    1. CATALOG_DATABASE_URL: Dedicated Vision catalog PostgreSQL URL.
       Highest priority. Normalized from postgres:// to postgresql://.
    2. Legacy DATABASE_URL: Preserved ONLY for standalone backward compatibility.
       Interpreted as Vision catalog DB ONLY when SHARED_DATABASE_URL is NOT configured.
    3. If SHARED_DATABASE_URL exists and CATALOG_DATABASE_URL is absent:
       Ignore DATABASE_URL for Vision catalog access and return None so callers
       fall back to local SQLite DATABASE_PATH.
    """
    # 1. Dedicated catalog URL takes highest priority
    catalog_url = os.getenv("CATALOG_DATABASE_URL")
    if catalog_url and catalog_url.strip():
        clean_url = catalog_url.strip()
        if clean_url.startswith("postgres://"):
            clean_url = "postgresql://" + clean_url[len("postgres://") :]
        return clean_url

    # 2. Legacy fallback: Only interpret DATABASE_URL as catalog DB when SHARED_DATABASE_URL is not configured
    shared_url = os.getenv("SHARED_DATABASE_URL")
    if not (shared_url and shared_url.strip()):
        legacy_url = os.getenv("DATABASE_URL")
        if legacy_url and legacy_url.strip():
            clean_legacy = legacy_url.strip()
            if clean_legacy.startswith("postgres://"):
                clean_legacy = "postgresql://" + clean_legacy[len("postgres://") :]
            return clean_legacy

    # 3. In unified integration mode (SHARED_DATABASE_URL configured) without CATALOG_DATABASE_URL,
    # ignore DATABASE_URL and return None so callers use SQLite DATABASE_PATH fallback.
    return None



def is_postgres() -> bool:
    """Check if the active configuration points to a PostgreSQL database."""
    url = get_database_url()
    return url is not None and url.startswith("postgresql://")


def get_db_path() -> Path:
    """Resolve SQLite database path for local development."""
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        path = Path(env_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    return DEFAULT_SQLITE_PATH


@contextmanager
def get_connection(
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Generator[Any, None, None]:
    """Provide a transactional database connection for either PostgreSQL or SQLite."""
    active_url = database_url if database_url is not None else get_database_url()

    if active_url and active_url.startswith("postgresql://"):
        if not HAS_POSTGRES:
            raise RuntimeError("psycopg2 is not installed. Please run `pip install psycopg2-binary`.")
        
        conn = psycopg2.connect(active_url)
        if HAS_PGVECTOR:
            try:
                pgvector.psycopg2.register_vector(conn)
            except Exception:
                pass
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        target_path = Path(db_path) if db_path is not None else get_db_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def initialize_database(
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    force_recreate: bool = False,
    embedding_dim: Optional[int] = None,
) -> None:
    """Initialize database schema, tables, indices, and pgvector extension."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor() as cur:
                # 1. Enable pgvector if available
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                except Exception as e:
                    logger.warning("Could not create pgvector extension: %s", e)

                # 2. Recreate table if requested
                if force_recreate:
                    cur.execute("DROP TABLE IF EXISTS catalog_items CASCADE;")
                    cur.execute("DROP VIEW IF EXISTS products CASCADE;")

                # Vector column type
                vec_col = f"vector({embedding_dim})" if embedding_dim and embedding_dim > 0 else "vector"

                pg_schema = f"""
                CREATE TABLE IF NOT EXISTS catalog_items (
                    id SERIAL PRIMARY KEY,
                    image_id INTEGER UNIQUE NOT NULL,
                    product_id INTEGER NOT NULL,
                    external_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    image_url TEXT,
                    relative_path TEXT NOT NULL,
                    category TEXT,
                    master_category TEXT,
                    sub_category TEXT,
                    article_type TEXT,
                    gender TEXT,
                    base_colour TEXT,
                    season TEXT,
                    year INTEGER,
                    usage TEXT,
                    product_display_name TEXT,
                    embedding {vec_col},
                    embedding_dimension INTEGER,
                    embedding_model TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_cat_image_id ON catalog_items(image_id);
                CREATE INDEX IF NOT EXISTS idx_cat_product_id ON catalog_items(product_id);
                CREATE INDEX IF NOT EXISTS idx_cat_category ON catalog_items(category);
                CREATE OR REPLACE VIEW products AS SELECT * FROM catalog_items;
                """
                cur.execute(pg_schema)
        else:
            # SQLite Schema
            schema = """
            CREATE TABLE IF NOT EXISTS catalog_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE NOT NULL,
                product_id INTEGER NOT NULL,
                external_id TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                image_url TEXT,
                relative_path TEXT NOT NULL,
                category TEXT,
                master_category TEXT,
                sub_category TEXT,
                article_type TEXT,
                gender TEXT,
                base_colour TEXT,
                season TEXT,
                year INTEGER,
                usage TEXT,
                product_display_name TEXT,
                embedding BLOB,
                embedding_dimension INTEGER,
                embedding_model TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cat_image_id ON catalog_items(image_id);
            CREATE INDEX IF NOT EXISTS idx_cat_product_id ON catalog_items(product_id);
            CREATE INDEX IF NOT EXISTS idx_cat_category ON catalog_items(category);
            CREATE TABLE IF NOT EXISTS products AS SELECT * FROM catalog_items WHERE 0;
            """
            if force_recreate:
                conn.execute("DROP TABLE IF EXISTS catalog_items;")
                conn.execute("DROP TABLE IF EXISTS products;")
                conn.execute("DROP VIEW IF EXISTS products;")
            conn.executescript(schema)


def bulk_insert_catalog_items(
    items: List[Dict[str, Any]],
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    batch_size: int = 5000,
) -> int:
    """Bulk insert catalog items into the database."""
    if not items:
        return 0

    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")
    now_ts = datetime.now(timezone.utc).isoformat()

    prepared = []
    for item in items:
        fn = item.get("filename") or Path(str(item.get("image_path", ""))).name
        img_url = item.get("image_url") or f"/catalog-images/{fn}"
        rel_p = item.get("relative_path") or item.get("image_path") or f"data/images/{fn}"
        ext_id = str(item.get("external_id") or item.get("image_id"))
        img_id = int(item.get("image_id"))
        prod_id = int(item.get("product_id") if item.get("product_id") is not None else img_id)

        rec = {
            "image_id": img_id,
            "product_id": prod_id,
            "external_id": ext_id,
            "filename": fn,
            "image_url": img_url,
            "relative_path": rel_p,
            "category": item.get("category") or item.get("master_category", ""),
            "master_category": item.get("master_category", ""),
            "sub_category": item.get("sub_category", ""),
            "article_type": item.get("article_type", ""),
            "gender": item.get("gender", ""),
            "base_colour": item.get("base_colour", ""),
            "season": item.get("season", ""),
            "year": int(item["year"]) if item.get("year") and str(item["year"]).isdigit() else None,
            "usage": item.get("usage", ""),
            "product_display_name": item.get("product_display_name", ""),
            "embedding_dimension": item.get("embedding_dimension"),
            "embedding_model": item.get("embedding_model"),
            "created_at": item.get("created_at") or now_ts,
            "updated_at": item.get("updated_at") or now_ts,
        }
        prepared.append(rec)

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor() as cur:
                columns = [
                    "image_id", "product_id", "external_id", "filename", "image_url",
                    "relative_path", "category", "master_category", "sub_category",
                    "article_type", "gender", "base_colour", "season", "year",
                    "usage", "product_display_name", "embedding_dimension",
                    "embedding_model", "created_at", "updated_at"
                ]
                insert_query = f"""
                INSERT INTO catalog_items ({', '.join(columns)})
                VALUES %s
                ON CONFLICT (image_id) DO NOTHING;
                """
                tuples = [tuple(r[c] for c in columns) for r in prepared]
                for i in range(0, len(tuples), batch_size):
                    chunk = tuples[i : i + batch_size]
                    extras.execute_values(cur, insert_query, chunk, page_size=batch_size)
        else:
            sql = """
            INSERT INTO catalog_items (
                image_id, product_id, external_id, filename, image_url,
                relative_path, category, master_category, sub_category,
                article_type, gender, base_colour, season, year,
                usage, product_display_name, embedding_dimension,
                embedding_model, created_at, updated_at
            ) VALUES (
                :image_id, :product_id, :external_id, :filename, :image_url,
                :relative_path, :category, :master_category, :sub_category,
                :article_type, :gender, :base_colour, :season, :year,
                :usage, :product_display_name, :embedding_dimension,
                :embedding_model, :created_at, :updated_at
            );
            """
            for i in range(0, len(prepared), batch_size):
                chunk = prepared[i : i + batch_size]
                conn.executemany(sql, chunk)

    return len(prepared)


def fetch_catalog_items_by_ids(
    item_ids: List[Union[int, np.integer]],
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve catalog items by primary key IDs, preserving the exact input order."""
    if not item_ids:
        return []

    clean_ids = [int(x) for x in item_ids]
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM catalog_items WHERE id = ANY(%s);",
                    (clean_ids,),
                )
                rows = [dict(r) for r in cur.fetchall()]
        else:
            placeholders = ",".join("?" for _ in clean_ids)
            cursor = conn.execute(
                f"SELECT * FROM catalog_items WHERE id IN ({placeholders});",
                clean_ids,
            )
            rows = [dict(r) for r in cursor.fetchall()]

    # Preserve input ranking order
    items_by_id = {row["id"]: row for row in rows}
    ordered_results = [items_by_id[iid] for iid in clean_ids if iid in items_by_id]
    return ordered_results


def get_catalog_item(
    item_id: int,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve a single catalog item by primary key ID."""
    items = fetch_catalog_items_by_ids([item_id], database_url=database_url, db_path=db_path)
    return items[0] if items else None


def get_catalog_items(
    item_ids: List[int],
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve multiple catalog items by primary key IDs, preserving input order."""
    return fetch_catalog_items_by_ids(item_ids, database_url=database_url, db_path=db_path)


def get_items_by_product(
    product_id: int,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all catalog items associated with a given product ID."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM catalog_items WHERE product_id = %s ORDER BY id ASC;",
                    (int(product_id),),
                )
                return [dict(r) for r in cur.fetchall()]
        else:
            cursor = conn.execute(
                "SELECT * FROM catalog_items WHERE product_id = ? ORDER BY id ASC;",
                (int(product_id),),
            )
            return [dict(r) for r in cursor.fetchall()]


def fetch_all_catalog_items(
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all catalog items ordered by primary key ID."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute("SELECT * FROM catalog_items ORDER BY id ASC;")
                return [dict(r) for r in cur.fetchall()]
        else:
            cursor = conn.execute("SELECT * FROM catalog_items ORDER BY id ASC;")
            return [dict(r) for r in cursor.fetchall()]


def get_catalog_count(
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> int:
    """Return total number of records in catalog_items table."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM catalog_items;")
                res = cur.fetchone()
                return res[0] if res else 0
        else:
            cursor = conn.execute("SELECT COUNT(*) as count FROM catalog_items;")
            row = cursor.fetchone()
            return row["count"] if row else 0


def update_production_embeddings_batch(
    id_to_vector_map: Dict[int, np.ndarray],
    model_name: str,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    batch_size: int = 2000,
) -> int:
    """Update embedding vectors for catalog items by primary key ID."""
    if not id_to_vector_map:
        return 0

    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    items = list(id_to_vector_map.items())
    total_updated = 0

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor() as cur:
                for i in range(0, len(items), batch_size):
                    chunk = items[i : i + batch_size]
                    update_data = [
                        (vec.tolist(), len(vec), model_name, cid)
                        for cid, vec in chunk
                    ]
                    query = """
                    UPDATE catalog_items SET
                        embedding = %s::vector,
                        embedding_dimension = %s,
                        embedding_model = %s,
                        updated_at = NOW()
                    WHERE id = %s;
                    """
                    cur.executemany(query, update_data)
                    total_updated += len(chunk)
        else:
            sql = """
            UPDATE catalog_items SET
                embedding = ?,
                embedding_dimension = ?,
                embedding_model = ?,
                updated_at = ?
            WHERE id = ?;
            """
            now_ts = datetime.now(timezone.utc).isoformat()
            for i in range(0, len(items), batch_size):
                chunk = items[i : i + batch_size]
                chunk_params = [
                    (vec.astype(np.float32).tobytes(), len(vec), model_name, now_ts, cid)
                    for cid, vec in chunk
                ]
                conn.executemany(sql, chunk_params)
                total_updated += len(chunk)

    return total_updated


def init_user_tables(
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> None:
    """Initialize users and search_history tables if they do not exist."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    username VARCHAR(100) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    salt VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    last_login TIMESTAMP WITH TIME ZONE
                );
                CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

                CREATE TABLE IF NOT EXISTS search_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    query_filename VARCHAR(255),
                    top_k INTEGER,
                    result_count INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                """)
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);")
            conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query_filename TEXT,
                top_k INTEGER,
                result_count INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            );
            """)


def create_db_user(
    email: str,
    username: str,
    password_hash: str,
    salt: str,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Create a new user record in the database."""
    init_user_tables(database_url=database_url, db_path=db_path)
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")
    now_ts = datetime.now(timezone.utc).isoformat()

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute("""
                INSERT INTO users (email, username, password_hash, salt, created_at, last_login)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                RETURNING id, email, username, created_at;
                """, (email.lower().strip(), username.strip(), password_hash, salt))
                row = dict(cur.fetchone())
                return row
        else:
            cursor = conn.execute("""
            INSERT INTO users (email, username, password_hash, salt, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (email.lower().strip(), username.strip(), password_hash, salt, now_ts, now_ts))
            user_id = cursor.lastrowid
            return {
                "id": user_id,
                "email": email.lower().strip(),
                "username": username.strip(),
                "created_at": now_ts,
            }


def get_db_user_by_email(
    email: str,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve user record including password hash by email."""
    init_user_tables(database_url=database_url, db_path=db_path)
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s;", (email.lower().strip(),))
                row = cur.fetchone()
                return dict(row) if row else None
        else:
            cursor = conn.execute("SELECT * FROM users WHERE email = ?;", (email.lower().strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None


def get_db_user_by_id(
    user_id: int,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve user record (sanitized) by user ID."""
    init_user_tables(database_url=database_url, db_path=db_path)
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute("SELECT id, email, username, created_at, last_login FROM users WHERE id = %s;", (int(user_id),))
                row = cur.fetchone()
                return dict(row) if row else None
        else:
            cursor = conn.execute("SELECT id, email, username, created_at, last_login FROM users WHERE id = ?;", (int(user_id),))
            row = cursor.fetchone()
            return dict(row) if row else None


def update_user_last_login(
    user_id: int,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> None:
    """Update last_login timestamp for a user."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s;", (int(user_id),))
        else:
            now_ts = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?;", (now_ts, int(user_id)))


CANONICAL_TOP_CATEGORIES: List[Dict[str, Any]] = [
    {
        "category_name": "Tshirts",
        "master_category": "Apparel",
        "item_count": 7022,
        "sample_filename": "10003.jpg",
        "sample_image_url": "/catalog-images/10003.jpg",
    },
    {
        "category_name": "Shirts",
        "master_category": "Apparel",
        "item_count": 3186,
        "sample_filename": "10051.jpg",
        "sample_image_url": "/catalog-images/10051.jpg",
    },
    {
        "category_name": "Casual Shoes",
        "master_category": "Footwear",
        "item_count": 2828,
        "sample_filename": "10127.jpg",
        "sample_image_url": "/catalog-images/10127.jpg",
    },
    {
        "category_name": "Watches",
        "master_category": "Accessories",
        "item_count": 2531,
        "sample_filename": "10098.jpg",
        "sample_image_url": "/catalog-images/10098.jpg",
    },
    {
        "category_name": "Sports Shoes",
        "master_category": "Footwear",
        "item_count": 2024,
        "sample_filename": "10035.jpg",
        "sample_image_url": "/catalog-images/10035.jpg",
    },
    {
        "category_name": "Kurtas",
        "master_category": "Apparel",
        "item_count": 1821,
        "sample_filename": "11534.jpg",
        "sample_image_url": "/catalog-images/11534.jpg",
    },
    {
        "category_name": "Tops",
        "master_category": "Apparel",
        "item_count": 1750,
        "sample_filename": "10324.jpg",
        "sample_image_url": "/catalog-images/10324.jpg",
    },
    {
        "category_name": "Handbags",
        "master_category": "Accessories",
        "item_count": 1741,
        "sample_filename": "10196.jpg",
        "sample_image_url": "/catalog-images/10196.jpg",
    },
]


def get_top_catalog_categories(
    limit: int = 8,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve top categories from the catalog with count and sample image."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    try:
        with get_connection(database_url=active_url, db_path=db_path) as conn:
            if use_pg:
                with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                    cur.execute("""
                    SELECT
                        COALESCE(article_type, category) as category_name,
                        category as master_category,
                        COUNT(*) as item_count,
                        MIN(filename) as sample_filename,
                        MIN(image_url) as sample_image_url
                    FROM catalog_items
                    WHERE article_type IS NOT NULL AND article_type != ''
                    GROUP BY COALESCE(article_type, category), category
                    ORDER BY item_count DESC
                    LIMIT %s;
                    """, (limit,))
                    results = [dict(r) for r in cur.fetchall()]
                    if results:
                        return results
            else:
                cursor = conn.execute("""
                SELECT
                    COALESCE(article_type, category) as category_name,
                    category as master_category,
                    COUNT(*) as item_count,
                    MIN(filename) as sample_filename,
                    MIN(image_url) as sample_image_url
                FROM catalog_items
                WHERE article_type IS NOT NULL AND article_type != ''
                GROUP BY COALESCE(article_type, category), category
                ORDER BY item_count DESC
                LIMIT ?;
                """, (limit,))
                results = [dict(r) for r in cursor.fetchall()]
                if results:
                    return results
    except Exception as e:
        logger.warning("Could not fetch top catalog categories from DB, falling back to defaults: %s", e)

    return CANONICAL_TOP_CATEGORIES[:limit]


def get_catalog_item_by_filename(
    filename: str,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve a single catalog item by filename (e.g. '10003.jpg') or image ID."""
    if not filename:
        return None
    safe_fn = os.path.basename(filename.strip())
    image_id_str = safe_fn.split(".")[0]
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")

    try:
        with get_connection(database_url=active_url, db_path=db_path) as conn:
            if use_pg:
                with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM catalog_items 
                        WHERE filename = %s 
                           OR filename = %s
                           OR CAST(image_id AS TEXT) = %s
                           OR CAST(product_id AS TEXT) = %s
                        LIMIT 1;
                        """,
                        (safe_fn, f"{image_id_str}.jpg", image_id_str, image_id_str),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM catalog_items 
                    WHERE filename = ? 
                       OR filename = ?
                       OR CAST(image_id AS TEXT) = ?
                       OR CAST(product_id AS TEXT) = ?
                    LIMIT 1;
                    """,
                    (safe_fn, f"{image_id_str}.jpg", image_id_str, image_id_str),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.warning("Error querying catalog item by filename %s: %s", filename, e)
        return None


def get_catalog_items_by_category(
    category_name: str,
    limit: int = 20,
    database_url: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve catalog items for a given category or article type."""
    active_url = database_url if database_url is not None else get_database_url()
    use_pg = active_url is not None and active_url.startswith("postgresql://")
    cat_clean = category_name.strip()

    with get_connection(database_url=active_url, db_path=db_path) as conn:
        if use_pg:
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute("""
                SELECT *
                FROM catalog_items
                WHERE LOWER(article_type) = LOWER(%s)
                   OR LOWER(category) = LOWER(%s)
                   OR LOWER(sub_category) = LOWER(%s)
                ORDER BY id ASC
                LIMIT %s;
                """, (cat_clean, cat_clean, cat_clean, limit))
                return [dict(r) for r in cur.fetchall()]
        else:
            cursor = conn.execute("""
            SELECT *
            FROM catalog_items
            WHERE LOWER(article_type) = LOWER(?)
               OR LOWER(category) = LOWER(?)
               OR LOWER(sub_category) = LOWER(?)
            ORDER BY id ASC
            LIMIT ?;
            """, (cat_clean, cat_clean, cat_clean, limit))
            return [dict(r) for r in cursor.fetchall()]
