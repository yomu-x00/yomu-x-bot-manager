"""FastAPI dependency injection providers (Dependency Inversion Principle).

High-level modules (routers) depend on these abstractions rather than
directly constructing database connections or reading environment variables.
"""

import os
import sqlite3
from pathlib import Path
from typing import Generator

from crypto import get_encryption_key
from db import get_connection


def get_db_path() -> Path:
    """Return the database path from environment or default."""
    return Path(os.environ.get("DATABASE_PATH", "/app/data/twitter.db"))


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a database connection and ensure it is closed after use."""
    conn = get_connection(get_db_path())
    try:
        yield conn
    finally:
        conn.close()


def get_key() -> bytes:
    """Return the AES-GCM encryption key."""
    return get_encryption_key()
