"""Tests for repository layer (AccountRepository, RuleRepository,
ScheduledPostRepository, MonitorRepository, LogRepository).
"""

import json
from datetime import datetime, timedelta

import pytest

from repositories import (
    AccountRepository,
    RuleRepository,
    ScheduledPostRepository,
    MonitorRepository,
    LogRepository,
)


# ---------------------------------------------------------------------------
# AccountRepository
# ---------------------------------------------------------------------------

class TestAccountRepository:
    def _insert_account(self, db_conn, name="Bot", username="bot"):
        repo = AccountRepository(db_conn)
        return repo.create(
            name=name,
            encrypted_token="enc_token",
            encrypted_ct0="enc_ct0",
            username=username,
            is_active=True,
        )

    def test_create_returns_row(self, db_conn):
        row = self._insert_account(db_conn)
        assert row["name"] == "Bot"
        assert row["username"] == "bot"
        assert row["is_active"]  # SQLite returns 1 for True
        assert "id" in row
        assert "created_at" in row

    def test_list_all_empty(self, db_conn):
        repo = AccountRepository(db_conn)
        assert repo.list_all() == []

    def test_list_all_returns_accounts(self, db_conn):
        self._insert_account(db_conn, name="A", username="a")
        self._insert_account(db_conn, name="B", username="b")
        repo = AccountRepository(db_conn)
        rows = repo.list_all()
        assert len(rows) == 2
        assert rows[0]["name"] == "A"
        assert rows[1]["name"] == "B"

    def test_list_all_does_not_expose_credentials(self, db_conn):
        self._insert_account(db_conn)
        rows = AccountRepository(db_conn).list_all()
        assert "auth_token" not in rows[0]
        assert "ct0" not in rows[0]

    def test_get_by_id_found(self, db_conn):
        created = self._insert_account(db_conn)
        row = AccountRepository(db_conn).get_by_id(created["id"])
        assert row is not None
        assert row["id"] == created["id"]

    def test_get_by_id_not_found(self, db_conn):
        assert AccountRepository(db_conn).get_by_id(999) is None

    def test_get_credentials(self, db_conn):
        created = self._insert_account(db_conn)
        creds = AccountRepository(db_conn).get_credentials(created["id"])
        assert creds is not None
        assert "auth_token" in creds
        assert "ct0" in creds

    def test_get_credentials_not_found(self, db_conn):
        assert AccountRepository(db_conn).get_credentials(999) is None

    def test_update_name(self, db_conn):
        created = self._insert_account(db_conn)
        updated = AccountRepository(db_conn).update(created["id"], {"name": "Updated"})
        assert updated["name"] == "Updated"

    def test_delete_existing(self, db_conn):
        created = self._insert_account(db_conn)
        rowcount = AccountRepository(db_conn).delete(created["id"])
        assert rowcount == 1
        assert AccountRepository(db_conn).get_by_id(created["id"]) is None

    def test_delete_nonexistent(self, db_conn):
        assert AccountRepository(db_conn).delete(999) == 0


# ---------------------------------------------------------------------------
# RuleRepository
# ---------------------------------------------------------------------------

class TestRuleRepository:
    def _insert_account(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.commit()
        return db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _insert_rule(self, db_conn, account_id, name="Rule1"):
        return RuleRepository(db_conn).create(
            account_id=account_id,
            name=name,
            is_active=True,
            trigger_type="keyword",
            trigger_config={"keywords": ["AI"]},
            action_type="like",
            action_config={},
            cooldown_minutes=60,
            daily_limit=50,
        )

    def test_create_parses_json_fields(self, db_conn):
        acct_id = self._insert_account(db_conn)
        rule = self._insert_rule(db_conn, acct_id)
        assert isinstance(rule["trigger_config"], dict)
        assert rule["trigger_config"]["keywords"] == ["AI"]
        assert isinstance(rule["action_config"], dict)

    def test_list_all_empty(self, db_conn):
        assert RuleRepository(db_conn).list_all() == []

    def test_list_all_with_account_filter(self, db_conn):
        acct_id = self._insert_account(db_conn)
        self._insert_rule(db_conn, acct_id, "R1")
        self._insert_rule(db_conn, acct_id, "R2")
        rules = RuleRepository(db_conn).list_all(account_id=acct_id)
        assert len(rules) == 2

    def test_list_all_account_filter_no_match(self, db_conn):
        acct_id = self._insert_account(db_conn)
        self._insert_rule(db_conn, acct_id)
        assert RuleRepository(db_conn).list_all(account_id=999) == []

    def test_get_by_id_not_found(self, db_conn):
        assert RuleRepository(db_conn).get_by_id(999) is None

    def test_update_daily_limit(self, db_conn):
        acct_id = self._insert_account(db_conn)
        rule = self._insert_rule(db_conn, acct_id)
        updated = RuleRepository(db_conn).update(rule["id"], {"daily_limit": 100})
        assert updated["daily_limit"] == 100

    def test_toggle_active(self, db_conn):
        acct_id = self._insert_account(db_conn)
        rule = self._insert_rule(db_conn, acct_id)
        assert rule["is_active"]  # SQLite returns 1 for True
        toggled = RuleRepository(db_conn).toggle_active(rule["id"], rule["is_active"])
        assert not toggled["is_active"]

    def test_delete_rule(self, db_conn):
        acct_id = self._insert_account(db_conn)
        rule = self._insert_rule(db_conn, acct_id)
        rowcount = RuleRepository(db_conn).delete(rule["id"])
        assert rowcount == 1

    def test_list_active_returns_active_only(self, db_conn):
        acct_id = self._insert_account(db_conn)
        r1 = self._insert_rule(db_conn, acct_id, "Active")
        r2 = self._insert_rule(db_conn, acct_id, "Inactive")
        RuleRepository(db_conn).toggle_active(r2["id"], True)  # disable r2

        active_rules = RuleRepository(db_conn).list_active()
        active_ids = [r["id"] for r in active_rules]
        assert r1["id"] in active_ids
        assert r2["id"] not in active_ids


# ---------------------------------------------------------------------------
# ScheduledPostRepository
# ---------------------------------------------------------------------------

class TestScheduledPostRepository:
    def _insert_account(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.commit()
        return db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _insert_post(self, db_conn, account_id, scheduled_at=None):
        if scheduled_at is None:
            scheduled_at = "2025-06-01T12:00:00"
        return ScheduledPostRepository(db_conn).create(
            account_id=account_id,
            content="Hello",
            scheduled_at=scheduled_at,
            repeat_type="none",
            repeat_config={},
        )

    def test_create_returns_row(self, db_conn):
        acct_id = self._insert_account(db_conn)
        post = self._insert_post(db_conn, acct_id)
        assert post["content"] == "Hello"
        assert post["status"] == "pending"
        assert isinstance(post["repeat_config"], dict)

    def test_list_all_empty(self, db_conn):
        assert ScheduledPostRepository(db_conn).list_all() == []

    def test_list_all_with_status_filter(self, db_conn):
        acct_id = self._insert_account(db_conn)
        post = self._insert_post(db_conn, acct_id)
        pending = ScheduledPostRepository(db_conn).list_all(status="pending")
        assert len(pending) == 1

        ScheduledPostRepository(db_conn).mark_posted(post["id"], "2025-06-01T12:01:00")
        pending_after = ScheduledPostRepository(db_conn).list_all(status="pending")
        assert len(pending_after) == 0

    def test_mark_failed(self, db_conn):
        acct_id = self._insert_account(db_conn)
        post = self._insert_post(db_conn, acct_id)
        ScheduledPostRepository(db_conn).mark_failed(post["id"])
        posts = ScheduledPostRepository(db_conn).list_all(status="failed")
        assert len(posts) == 1

    def test_delete_post(self, db_conn):
        acct_id = self._insert_account(db_conn)
        post = self._insert_post(db_conn, acct_id)
        rowcount = ScheduledPostRepository(db_conn).delete(post["id"])
        assert rowcount == 1
        assert ScheduledPostRepository(db_conn).list_all() == []

    def test_schedule_repeat(self, db_conn):
        acct_id = self._insert_account(db_conn)
        self._insert_post(db_conn, acct_id, "2025-06-01T12:00:00")
        ScheduledPostRepository(db_conn).schedule_repeat(
            account_id=acct_id,
            content="Hello",
            next_time_iso="2025-06-02T12:00:00",
            repeat_type="daily",
            repeat_config={},
        )
        all_posts = ScheduledPostRepository(db_conn).list_all()
        assert len(all_posts) == 2
        assert any(p["scheduled_at"] == "2025-06-02T12:00:00" for p in all_posts)

    def test_list_pending_due(self, db_conn):
        acct_id = self._insert_account(db_conn)
        # One past post, one future post
        self._insert_post(db_conn, acct_id, "2000-01-01T00:00:00")
        self._insert_post(db_conn, acct_id, "2099-01-01T00:00:00")

        due = ScheduledPostRepository(db_conn).list_pending_due(
            datetime.now().isoformat()
        )
        assert len(due) == 1
        assert due[0]["scheduled_at"] == "2000-01-01T00:00:00"


# ---------------------------------------------------------------------------
# MonitorRepository
# ---------------------------------------------------------------------------

class TestMonitorRepository:
    def _insert_account(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.commit()
        return db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def test_list_all_empty(self, db_conn):
        assert MonitorRepository(db_conn).list_all() == []

    def test_create_monitor(self, db_conn):
        acct_id = self._insert_account(db_conn)
        monitor = MonitorRepository(db_conn).create(
            account_id=acct_id,
            keyword="AI",
            notify_discord=False,
            discord_webhook=None,
            is_active=True,
        )
        assert monitor["keyword"] == "AI"
        assert monitor["is_active"]  # SQLite returns 1 for True

    def test_list_all_returns_monitors(self, db_conn):
        acct_id = self._insert_account(db_conn)
        MonitorRepository(db_conn).create(acct_id, "AI", False, None, True)
        MonitorRepository(db_conn).create(acct_id, "ML", False, None, True)
        monitors = MonitorRepository(db_conn).list_all()
        assert len(monitors) == 2


# ---------------------------------------------------------------------------
# LogRepository
# ---------------------------------------------------------------------------

class TestLogRepository:
    def _setup(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (1, 'rule', 'keyword', 'like')"""
        )
        db_conn.commit()

    def test_insert_and_list(self, db_conn):
        self._setup(db_conn)
        LogRepository(db_conn).insert(1, 1, "tweet1", "like", "success")
        logs = LogRepository(db_conn).list_logs()
        assert len(logs) == 1
        assert logs[0]["tweet_id"] == "tweet1"
        assert logs[0]["status"] == "success"

    def test_list_logs_filter_by_status(self, db_conn):
        self._setup(db_conn)
        LogRepository(db_conn).insert(1, 1, "t1", "like", "success")
        LogRepository(db_conn).insert(1, 1, "t2", "like", "failed")
        logs = LogRepository(db_conn).list_logs(status="success")
        assert len(logs) == 1
        assert logs[0]["tweet_id"] == "t1"

    def test_list_logs_filter_by_action(self, db_conn):
        self._setup(db_conn)
        LogRepository(db_conn).insert(1, 1, "t1", "like", "success")
        LogRepository(db_conn).insert(1, 1, "t2", "rt", "success")
        logs = LogRepository(db_conn).list_logs(action="rt")
        assert len(logs) == 1
        assert logs[0]["tweet_id"] == "t2"

    def test_list_logs_pagination(self, db_conn):
        self._setup(db_conn)
        for i in range(5):
            LogRepository(db_conn).insert(1, 1, f"t{i}", "like", "success")
        page1 = LogRepository(db_conn).list_logs(limit=2, offset=0)
        page2 = LogRepository(db_conn).list_logs(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["tweet_id"] != page2[0]["tweet_id"]

    def test_get_today_success_count(self, db_conn):
        self._setup(db_conn)
        LogRepository(db_conn).insert(1, 1, "t1", "like", "success")
        LogRepository(db_conn).insert(1, 1, "t2", "like", "failed")
        count = LogRepository(db_conn).get_today_success_count(1)
        assert count == 1

    def test_get_last_execution_time_none(self, db_conn):
        self._setup(db_conn)
        result = LogRepository(db_conn).get_last_execution_time(1, "unknown_tweet")
        assert result is None

    def test_get_last_execution_time_returns_datetime(self, db_conn):
        self._setup(db_conn)
        LogRepository(db_conn).insert(1, 1, "t1", "like", "success")
        result = LogRepository(db_conn).get_last_execution_time(1, "t1")
        assert isinstance(result, datetime)

    def test_get_today_stats(self, db_conn):
        self._setup(db_conn)
        LogRepository(db_conn).insert(1, 1, "t1", "like", "success")
        LogRepository(db_conn).insert(1, 1, "t2", "like", "failed")
        LogRepository(db_conn).insert(1, 1, "t3", "like", "skipped")
        from datetime import date
        stats = LogRepository(db_conn).get_today_stats(date.today().isoformat())
        assert stats["success"] == 1
        assert stats["failed"] == 1
        assert stats["skipped"] == 1
