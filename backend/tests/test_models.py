"""Tests for Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from models import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    RuleCreate,
    RuleResponse,
    ScheduledPostCreate,
    MonitorCreate,
    StatsResponse,
)


class TestAccountModels:
    def test_account_create_minimal(self):
        account = AccountCreate(
            name="bot", auth_token="tok", ct0="ct0", username="user"
        )
        assert account.is_active is True

    def test_account_create_full(self):
        account = AccountCreate(
            name="bot",
            auth_token="tok",
            ct0="ct0",
            username="user",
            is_active=False,
        )
        assert account.is_active is False

    def test_account_create_missing_required(self):
        with pytest.raises(ValidationError):
            AccountCreate(name="bot")

    def test_account_update_partial(self):
        update = AccountUpdate(name="new name")
        assert update.name == "new name"
        assert update.auth_token is None

    def test_account_response(self):
        resp = AccountResponse(
            id=1,
            name="bot",
            username="user",
            is_active=True,
            interval_minutes=5,
            created_at=datetime(2025, 1, 1),
        )
        assert resp.id == 1


class TestRuleModels:
    def test_rule_create_defaults(self):
        rule = RuleCreate(
            account_id=1,
            name="test",
            trigger_type="keyword",
            action_type="like",
        )
        assert rule.cooldown_minutes == 60
        assert rule.daily_limit == 50
        assert rule.trigger_config == {}

    def test_rule_create_with_config(self):
        rule = RuleCreate(
            account_id=1,
            name="test",
            trigger_type="keyword",
            trigger_config={"keywords": ["AI"]},
            action_type="rt",
        )
        assert rule.trigger_config["keywords"] == ["AI"]


class TestScheduledPostModels:
    def test_scheduled_post_defaults(self):
        post = ScheduledPostCreate(
            account_id=1,
            content="Hello",
            scheduled_at=datetime(2025, 6, 1, 12, 0),
        )
        assert post.repeat_type == "none"


class TestMonitorModels:
    def test_monitor_create(self):
        monitor = MonitorCreate(account_id=1, keyword="AI")
        assert monitor.notify_discord is False
        assert monitor.discord_webhook is None


class TestStatsResponse:
    def test_stats(self):
        stats = StatsResponse(
            total_accounts=2,
            active_accounts=1,
            total_rules=5,
            active_rules=3,
            pending_posts=2,
            today_executions=100,
            today_success=90,
            today_failed=5,
            today_skipped=5,
        )
        assert stats.today_success == 90
