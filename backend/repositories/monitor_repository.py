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
