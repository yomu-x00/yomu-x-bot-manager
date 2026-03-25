"""Tests for scheduled post processing."""

import json
from datetime import datetime, timedelta

import pytest

from scheduler import _schedule_next_repeat


class TestScheduleNextRepeat:
    def _make_post_row(self, db_conn, repeat_type="none", repeat_config=None, scheduled_at=None):
        """Helper to insert and return a scheduled post row."""
        if scheduled_at is None:
            scheduled_at = datetime.now().isoformat()
        if repeat_config is None:
            repeat_config = {}

        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.execute(
            """INSERT INTO scheduled_posts (account_id, content, scheduled_at, repeat_type, repeat_config, status)
            VALUES (?, ?, ?, ?, ?, 'posted')""",
            (1, "Hello", scheduled_at, repeat_type, json.dumps(repeat_config)),
        )
        db_conn.commit()

        cursor = db_conn.execute("SELECT * FROM scheduled_posts WHERE id = 1")
        return cursor.fetchone()

    def test_no_repeat(self, db_conn):
        post = self._make_post_row(db_conn, repeat_type="none")
        _schedule_next_repeat(db_conn, post)
        cursor = db_conn.execute("SELECT COUNT(*) FROM scheduled_posts")
        assert cursor.fetchone()[0] == 1  # No new row

    def test_daily_repeat(self, db_conn):
        base_time = datetime(2025, 6, 1, 12, 0)
        post = self._make_post_row(
            db_conn, repeat_type="daily", scheduled_at=base_time.isoformat()
        )
        _schedule_next_repeat(db_conn, post)

        cursor = db_conn.execute(
            "SELECT * FROM scheduled_posts WHERE status = 'pending'"
        )
        new_post = cursor.fetchone()
        assert new_post is not None
        next_time = datetime.fromisoformat(new_post["scheduled_at"])
        assert next_time == base_time + timedelta(days=1)

    def test_weekly_repeat(self, db_conn):
        base_time = datetime(2025, 6, 1, 12, 0)
        post = self._make_post_row(
            db_conn, repeat_type="weekly", scheduled_at=base_time.isoformat()
        )
        _schedule_next_repeat(db_conn, post)

        cursor = db_conn.execute(
            "SELECT * FROM scheduled_posts WHERE status = 'pending'"
        )
        new_post = cursor.fetchone()
        next_time = datetime.fromisoformat(new_post["scheduled_at"])
        assert next_time == base_time + timedelta(weeks=1)

    def test_custom_repeat(self, db_conn):
        base_time = datetime(2025, 6, 1, 12, 0)
        post = self._make_post_row(
            db_conn,
            repeat_type="custom",
            repeat_config={"interval_hours": 6},
            scheduled_at=base_time.isoformat(),
        )
        _schedule_next_repeat(db_conn, post)

        cursor = db_conn.execute(
            "SELECT * FROM scheduled_posts WHERE status = 'pending'"
        )
        new_post = cursor.fetchone()
        next_time = datetime.fromisoformat(new_post["scheduled_at"])
        assert next_time == base_time + timedelta(hours=6)
