"""Database service for managing catalog metadata in SQLite."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, List, Optional

# Resolve project root and default database path dynamically
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "catalog.db"


def get_db_path() -> Path:
    """Dynamically resolve the SQLite database file path from environment or default."""
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        path = Path(env_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    return DEFAULT_DB_PATH


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional context manager for SQLite database connections.

    Args:
        db_path: Optional path override for database file.

    Yields:
        sqlite3.Connection: Active SQLite connection object.
    """
    target_path = db_path if db_path is not None else get_db_path()
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


def initialize_database(db_path: Optional[Path] = None) -> None:
    """Initialize the database schema by creating the products table if missing.

    Args:
        db_path: Optional database path override.
    """
    schema = """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_id TEXT UNIQUE,
        image_path TEXT UNIQUE,
        filename TEXT,
        category TEXT,
        embedding_dimension INTEGER,
        created_at TEXT
    );
    """
    try:
        with get_connection(db_path) as conn:
            conn.execute(schema)
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to initialize database: {e}") from e


def upsert_product(
    external_id: str,
    image_path: str,
    filename: Optional[str] = None,
    category: Optional[str] = None,
    embedding_dimension: Optional[int] = 512,
    created_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Insert or update a product record in the products table.

    Args:
        external_id: Unique string identifier for product.
        image_path: Unique path to product image file.
        filename: Optional image file name.
        category: Optional product category.
        embedding_dimension: Dimension of image embedding (default 512).
        created_at: ISO formatted creation timestamp string.
        db_path: Optional database path override.

    Returns:
        int: Primary key ID of inserted or updated product record.
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    if filename is None:
        filename = Path(image_path).name

    sql = """
    INSERT INTO products (external_id, image_path, filename, category, embedding_dimension, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(external_id) DO UPDATE SET
        image_path = excluded.image_path,
        filename = excluded.filename,
        category = excluded.category,
        embedding_dimension = excluded.embedding_dimension,
        created_at = excluded.created_at
    RETURNING id;
    """

    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                sql,
                (
                    external_id,
                    image_path,
                    filename,
                    category,
                    embedding_dimension,
                    created_at,
                ),
            )
            row = cursor.fetchone()
            if row:
                return row["id"]
            return cursor.lastrowid
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to upsert product '{external_id}': {e}") from e


def fetch_all_products(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve all product records from the database.

    Args:
        db_path: Optional database path override.

    Returns:
        List[Dict[str, Any]]: List of dictionary representations of product rows.
    """
    sql = "SELECT id, external_id, image_path, filename, category, embedding_dimension, created_at FROM products;"
    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to fetch products: {e}") from e


def get_product_count(db_path: Optional[Path] = None) -> int:
    """Return total count of product records in the database.

    Args:
        db_path: Optional database path override.

    Returns:
        int: Total count of product records.
    """
    sql = "SELECT COUNT(*) as count FROM products;"
    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(sql)
            row = cursor.fetchone()
            return row["count"] if row else 0
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to count products: {e}") from e
