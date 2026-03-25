"""Tests for database initialization and schema."""

from db import get_connection, init_db


def test_init_db_creates_tables(db_path):
    """All expected tables should be created."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()

    assert "accounts" in tables
    assert "rules" in tables
    assert "scheduled_posts" in tables
    assert "rule_logs" in tables
    assert "monitors" in tables


def test_init_db_is_idempotent(db_path):
    """Running init_db twice should not raise errors."""
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()
    assert "accounts" in tables


def test_foreign_keys_enabled(db_conn):
    """Foreign keys should be enabled."""
    cursor = db_conn.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1


def test_wal_mode(db_conn):
    """WAL journal mode should be set."""
    cursor = db_conn.execute("PRAGMA journal_mode")
    assert cursor.fetchone()[0] == "wal"


def test_insert_account(db_conn):
    """Basic account insertion should work."""
    db_conn.execute(
        "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
        ("test bot", "token123", "ct0123", "testuser"),
    )
    db_conn.commit()

    cursor = db_conn.execute("SELECT * FROM accounts WHERE username = 'testuser'")
    row = cursor.fetchone()
    assert row["name"] == "test bot"
    assert row["is_active"] == 1


def test_insert_rule_with_fk(db_conn):
    """Rule insertion should respect foreign key constraint."""
    db_conn.execute(
        "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
        ("bot", "t", "c", "user"),
    )
    db_conn.execute(
        """INSERT INTO rules (account_id, name, trigger_type, trigger_config, action_type)
        VALUES (1, 'test rule', 'keyword', '{"keywords":["AI"]}', 'like')"""
    )
    db_conn.commit()

    cursor = db_conn.execute("SELECT * FROM rules WHERE name = 'test rule'")
    row = cursor.fetchone()
    assert row["trigger_type"] == "keyword"
    assert row["daily_limit"] == 50


def test_rule_fk_constraint(db_conn):
    """Inserting a rule with invalid account_id should fail."""
    import sqlite3
    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (999, 'bad rule', 'keyword', 'like')"""
        )


def test_trigger_type_check_constraint(db_conn):
    """Invalid trigger_type should be rejected."""
    import sqlite3
    import pytest

    db_conn.execute(
        "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
        ("bot", "t", "c", "user"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (1, 'bad', 'invalid_type', 'like')"""
        )
