"""Repository for rule logs and statistics (Single Responsibility Principle)."""

import sqlite3
from datetime import date, datetime
from typing import Any


class LogRepository:
    """Encapsulates all database queries related to rule execution logs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_logs(
        self,
        account_id: int | None = None,
        rule_id: int | None = None,
        action: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return execution logs with optional filters and pagination."""
        query = "SELECT * FROM rule_logs WHERE 1=1"
        params: list[Any] = []

        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if rule_id:
            query += " AND rule_id = ?"
            params.append(rule_id)
        if action:
            query += " AND action = ?"
            params.append(action)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY executed_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self._conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def insert(
        self,
        rule_id: int,
        account_id: int,
        tweet_id: str | None,
        action: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        """Record an execution log entry."""
        self._conn.execute(
            """INSERT INTO rule_logs
            (rule_id, account_id, tweet_id, action, status, reason)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (rule_id, account_id, tweet_id, action, status, reason),
        )
        self._conn.commit()

    def get_today_success_count(self, rule_id: int) -> int:
        """Return the number of successful executions for a rule today."""
        today = date.today().isoformat()
        cursor = self._conn.execute(
            """SELECT COUNT(*) FROM rule_logs
            WHERE rule_id = ? AND status = 'success'
            AND date(executed_at) = ?""",
            (rule_id, today),
        )
        return cursor.fetchone()[0]

    def get_last_execution_time(
        self, rule_id: int, tweet_id: str
    ) -> datetime | None:
        """Return the last successful execution time for a rule-tweet pair."""
        cursor = self._conn.execute(
            """SELECT executed_at FROM rule_logs
            WHERE rule_id = ? AND tweet_id = ? AND status = 'success'
            ORDER BY executed_at DESC LIMIT 1""",
            (rule_id, tweet_id),
        )
        row = cursor.fetchone()
        if row:
            return datetime.fromisoformat(row[0])
        return None

    def get_today_stats(self, today_iso: str, account_id: int | None = None) -> dict[str, int]:
        """Return status counts for today's executions, optionally filtered by account."""
        if account_id:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) as cnt FROM rule_logs WHERE date(executed_at) = ? AND account_id = ? GROUP BY status",
                (today_iso, account_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) as cnt FROM rule_logs WHERE date(executed_at) = ? GROUP BY status",
                (today_iso,),
            ).fetchall()
        stats: dict[str, int] = {"success": 0, "failed": 0, "skipped": 0}
        for row in rows:
            stats[row["status"]] = row["cnt"]
        return stats
