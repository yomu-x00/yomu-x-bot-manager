"""Repository for monitor data access (Single Responsibility Principle)."""

import sqlite3
from typing import Any


class MonitorRepository:
    """Encapsulates all database queries related to monitors."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[dict[str, Any]]:
        """Return all monitors ordered by id."""
        cursor = self._conn.execute("SELECT * FROM monitors ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, monitor_id: int) -> dict[str, Any] | None:
        """Return a single monitor row, or None."""
        row = self._conn.execute(
            "SELECT * FROM monitors WHERE id = ?", (monitor_id,)
        ).fetchone()
        return dict(row) if row else None

    def create(
        self,
        account_id: int,
        keyword: str,
        notify_discord: bool,
        discord_webhook: str | None,
        is_active: bool,
    ) -> dict[str, Any]:
        """Insert a new monitor and return the created row."""
        cursor = self._conn.execute(
            """INSERT INTO monitors
            (account_id, keyword, notify_discord, discord_webhook, is_active)
            VALUES (?, ?, ?, ?, ?)""",
            (account_id, keyword, notify_discord, discord_webhook, is_active),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM monitors WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)

    def update(self, monitor_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial update and return the updated row."""
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [monitor_id]
        self._conn.execute(f"UPDATE monitors SET {set_clause} WHERE id = ?", values)
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM monitors WHERE id = ?", (monitor_id,)
        ).fetchone()
        return dict(row)

    def toggle_active(self, monitor_id: int, current_state: bool) -> dict[str, Any]:
        """Flip is_active and return the updated row."""
        self._conn.execute(
            "UPDATE monitors SET is_active = ? WHERE id = ?", (not current_state, monitor_id)
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM monitors WHERE id = ?", (monitor_id,)
        ).fetchone()
        return dict(row)

    def delete(self, monitor_id: int) -> int:
        """Delete a monitor and return the number of deleted rows."""
        result = self._conn.execute(
            "DELETE FROM monitors WHERE id = ?", (monitor_id,)
        )
        self._conn.commit()
        return result.rowcount
