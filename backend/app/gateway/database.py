import logging
import os
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# Explicitly load environment variables from backend/.env relative to this file
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
env_file_found = ENV_PATH.is_file()
load_dotenv(dotenv_path=ENV_PATH)

if env_file_found:
    logger.info(f"Loaded environment variables from '{ENV_PATH}' (found={env_file_found}).")
    print(f"[database] Loaded environment variables from '{ENV_PATH}' (found={env_file_found}).")
else:
    logger.warning(f"Environment file NOT found at '{ENV_PATH}' (found={env_file_found}). Relying on system environment.")
    print(f"[database] WARNING: Environment file NOT found at '{ENV_PATH}' (found={env_file_found}).")

# Check for DATABASE_URL; default to SQLite in-memory / local fallback if not configured
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or os.getenv("SHARED_DATABASE_URL", "").strip()

if DATABASE_URL:
    # Standardize postgres dialect for SQLAlchemy
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    # Configure engine for PostgreSQL (with connection pooling)
    if "postgresql" in DATABASE_URL:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=10,
            max_overflow=20,
            pool_timeout=45,
            connect_args={"connect_timeout": 45},
        )
    else:
        engine = create_engine(DATABASE_URL)
    logger.info("Database engine initialized for PostgreSQL/remote database.")
    print("[database] Database engine initialized for PostgreSQL/remote database.")
else:
    # Fallback to local SQLite database when DATABASE_URL is not set
    DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[3] / "ai_assistant.db"
    SQLITE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
    )
    logger.warning(f"DATABASE_URL not set; falling back to local SQLite at '{DEFAULT_SQLITE_PATH}'")
    print(f"[database] WARNING: DATABASE_URL not set; falling back to local SQLite at '{DEFAULT_SQLITE_PATH}'")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """Dependency for obtaining a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def init_db(target_engine=None) -> None:
    """Create all database tables for gateway and shared schemas."""
    e = target_engine or engine
    Base.metadata.create_all(bind=e)
