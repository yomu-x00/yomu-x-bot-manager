"""Repository for scheduled post data access (Single Responsibility Principle)."""

import json
import sqlite3
from typing import Any


def _parse_post_row(row: sqlite3.Row) -> dict[str, Any]:
    """Deserialize JSON fields of a scheduled post row."""
    d = dict(row)
    d["repeat_config"] = json.loads(d["repeat_config"]) if isinstance(d["repeat_config"], str) else d["repeat_config"]
    d["image_paths"] = json.loads(d["image_paths"]) if isinstance(d.get("image_paths"), str) else (d.get("image_paths") or [])
    return d


class ScheduledPostRepository:
    """Encapsulates all database queries related to scheduled posts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return all posts, optionally filtered by status."""
        if status:
            cursor = self._conn.execute(
                "SELECT * FROM scheduled_posts WHERE status = ? ORDER BY scheduled_at",
                (status,),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM scheduled_posts ORDER BY scheduled_at"
            )
        return [_parse_post_row(row) for row in cursor.fetchall()]

    def list_pending_due(self, now_iso: str) -> list[sqlite3.Row]:
        """Return pending posts that are due, joined with account credentials."""
        cursor = self._conn.execute(
            """SELECT sp.*, a.auth_token, a.ct0, a.tweet_suffix, a.platform
            FROM scheduled_posts sp
            JOIN accounts a ON sp.account_id = a.id
            WHERE sp.status = 'pending'
            AND sp.scheduled_at <= ?
            AND a.is_active = 1
            ORDER BY sp.scheduled_at ASC""",
            (now_iso,),
        )
        return cursor.fetchall()

    def get_by_id(self, post_id: int) -> dict[str, Any] | None:
        """Return a single scheduled post row, or None."""
        row = self._conn.execute(
            "SELECT * FROM scheduled_posts WHERE id = ?", (post_id,)
        ).fetchone()
        return _parse_post_row(row) if row else None

    def get_with_credentials(self, post_id: int) -> sqlite3.Row | None:
        """Return a single scheduled post joined with its account credentials."""
        return self._conn.execute(
            """SELECT sp.*, a.auth_token, a.ct0, a.tweet_suffix, a.platform
            FROM scheduled_posts sp
            JOIN accounts a ON sp.account_id = a.id
            WHERE sp.id = ?""",
            (post_id,),
        ).fetchone()

    def update(self, post_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial update to a pending post and return the updated row."""
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [post_id]
        self._conn.execute(f"UPDATE scheduled_posts SET {set_clause} WHERE id = ?", values)
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM scheduled_posts WHERE id = ?", (post_id,)
        ).fetchone()
        return _parse_post_row(row)

    def create(
        self,
        account_id: int,
        content: str,
        scheduled_at: str,
        repeat_type: str,
        repeat_config: dict,
        image_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """Insert a new scheduled post and return the created row."""
        cursor = self._conn.execute(
            """INSERT INTO scheduled_posts
            (account_id, content, scheduled_at, repeat_type, repeat_config, image_paths)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, content, scheduled_at, repeat_type, json.dumps(repeat_config), json.dumps(image_paths or [])),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM scheduled_posts WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _parse_post_row(row)

    def mark_posted(self, post_id: int, posted_at: str, posted_uri: str | None = None) -> None:
        """Update a post's status to 'posted'."""
        self._conn.execute(
            "UPDATE scheduled_posts SET status = 'posted', posted_at = ?, posted_uri = ? WHERE id = ?",
            (posted_at, posted_uri, post_id),
        )
        self._conn.commit()

    def mark_failed(self, post_id: int) -> None:
        """Update a post's status to 'failed'."""
        self._conn.execute(
            "UPDATE scheduled_posts SET status = 'failed' WHERE id = ?", (post_id,)
        )
        self._conn.commit()

    def schedule_repeat(
        self,
        account_id: int,
        content: str,
        next_time_iso: str,
        repeat_type: str,
        repeat_config: dict,
    ) -> None:
        """Insert the next occurrence of a repeating post."""
        self._conn.execute(
            """INSERT INTO scheduled_posts
            (account_id, content, scheduled_at, repeat_type, repeat_config, status)
            VALUES (?, ?, ?, ?, ?, 'pending')""",
            (account_id, content, next_time_iso, repeat_type, json.dumps(repeat_config)),
        )
        self._conn.commit()

    def delete(self, post_id: int) -> int:
        """Delete a scheduled post and return the number of deleted rows."""
        result = self._conn.execute(
            "DELETE FROM scheduled_posts WHERE id = ?", (post_id,)
        )
        self._conn.commit()
        return result.rowcount
