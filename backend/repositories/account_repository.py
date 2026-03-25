"""Repository for account data access (Single Responsibility Principle)."""

import sqlite3
from typing import Any


class AccountRepository:
    """Encapsulates all database queries related to accounts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[dict[str, Any]]:
        """Return all accounts ordered by id."""
        cursor = self._conn.execute(
            "SELECT id, name, username, is_active, created_at FROM accounts ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, account_id: int) -> dict[str, Any] | None:
        """Return a single account row including credentials, or None."""
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_credentials(self, account_id: int) -> dict[str, Any] | None:
        """Return auth_token and ct0 for a single account, or None."""
        row = self._conn.execute(
            "SELECT auth_token, ct0 FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return dict(row) if row else None

    def create(
        self,
        name: str,
        encrypted_token: str,
        encrypted_ct0: str,
        username: str,
        is_active: bool,
    ) -> dict[str, Any]:
        """Insert a new account and return the created row."""
        cursor = self._conn.execute(
            """INSERT INTO accounts (name, auth_token, ct0, username, is_active)
            VALUES (?, ?, ?, ?, ?)""",
            (name, encrypted_token, encrypted_ct0, username, is_active),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id, name, username, is_active, created_at FROM accounts WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)

    def update(self, account_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial update and return the updated row."""
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [account_id]
        self._conn.execute(f"UPDATE accounts SET {set_clause} WHERE id = ?", values)
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id, name, username, is_active, created_at FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return dict(row)

    def delete(self, account_id: int) -> int:
        """Delete an account and return the number of deleted rows."""
        result = self._conn.execute(
            "DELETE FROM accounts WHERE id = ?", (account_id,)
        )
        self._conn.commit()
        return result.rowcount
