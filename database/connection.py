from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    # database/connection.py -> project root
    return Path(__file__).resolve().parents[1]


def _db_path() -> Path:
    data_dir = _project_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "movies.db"


def get_connection() -> sqlite3.Connection:
    """
    Create and return a SQLite connection to `data/movies.db`.

    Notes:
    - Foreign keys are enabled.
    - `row_factory` is set to `sqlite3.Row` for dict-like access.
    """

    db_file = _db_path()
    try:
        conn = sqlite3.connect(db_file)
    except sqlite3.Error:
        logger.exception("Failed to connect to SQLite database at %s", db_file)
        raise

    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
    except sqlite3.Error:
        conn.close()
        logger.exception("Failed to configure SQLite connection")
        raise

    return conn


def initialize_database() -> None:
    """
    Initialize the SQLite database using `database/schema.sql`.
    Safe to call multiple times.
    """

    schema_path = Path(__file__).resolve().with_name("schema.sql")
    try:
        schema_sql = schema_path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("Failed to read schema file at %s", schema_path)
        raise

    with get_connection() as conn:
        try:
            conn.executescript(schema_sql)
            conn.commit()
            logger.info("Database initialized (schema applied).")
        except sqlite3.OperationalError as e:
            # If schema isn't using IF NOT EXISTS (or a local edit removed it),
            # keep this idempotent initializer resilient.
            if "already exists" in str(e).lower():
                logger.info("Database already initialized; schema objects exist.")
                return
            logger.exception("Failed to initialize database schema")
            raise
        except sqlite3.Error:
            logger.exception("Failed to initialize database schema")
            raise


@contextmanager
def database_session() -> Iterator[sqlite3.Connection]:
    """
    Context manager for a database session.

    - Commits automatically on success
    - Rolls back on exception
    - Always closes the connection

    Example:

        from database.connection import database_session, initialize_database

        initialize_database()

        with database_session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO movies (id, title) VALUES (?, ?)",
                (550, "Fight Club"),
            )
    """

    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        finally:
            logger.exception("Rolling back transaction due to exception")
        raise
    finally:
        conn.close()

