"""Shared test fixtures."""

import tempfile
from pathlib import Path

import pytest

from db import get_connection, init_db


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def db_conn(db_path):
    """Create a database connection for testing."""
    conn = get_connection(db_path)
    yield conn
    conn.close()
