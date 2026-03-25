"""Tests for FastAPI API endpoints."""

import base64
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

# Generate a test encryption key
_test_key = AESGCM.generate_key(bit_length=256)
_test_key_b64 = base64.b64encode(_test_key).decode()


@pytest.fixture(autouse=True)
def setup_env(tmp_path, monkeypatch):
    """Set up environment for all tests."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ENCRYPTION_KEY", _test_key_b64)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    # Patch DB_PATH and scheduler before importing app
    import main
    monkeypatch.setattr(main, "DB_PATH", db_path)

    from db import init_db
    init_db(db_path)

    yield


@pytest.fixture
def client():
    """Create a test client with scheduler disabled."""
    import main
    # Disable scheduler for tests
    with patch.object(main.scheduler, "start"), patch.object(main.scheduler, "shutdown"), \
         patch.object(main.scheduler, "add_job"):
        with TestClient(main.app) as c:
            yield c


class TestAccountEndpoints:
    def test_list_accounts_empty(self, client):
        resp = client.get("/api/accounts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_account(self, client):
        resp = client.post("/api/accounts", json={
            "name": "Test Bot",
            "auth_token": "secret_token",
            "ct0": "secret_ct0",
            "username": "testbot",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Bot"
        assert data["username"] == "testbot"
        assert data["is_active"] is True
        # auth_token and ct0 should NOT be in response
        assert "auth_token" not in data
        assert "ct0" not in data

    def test_list_accounts_after_create(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })
        resp = client.get("/api/accounts")
        assert len(resp.json()) == 1

    def test_update_account(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })
        resp = client.put("/api/accounts/1", json={"name": "Updated Bot"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Bot"

    def test_update_nonexistent(self, client):
        resp = client.put("/api/accounts/999", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_account(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })
        resp = client.delete("/api/accounts/1")
        assert resp.status_code == 204

        resp = client.get("/api/accounts")
        assert resp.json() == []

    def test_delete_nonexistent(self, client):
        resp = client.delete("/api/accounts/999")
        assert resp.status_code == 404


class TestRuleEndpoints:
    def _create_account(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })

    def test_create_rule(self, client):
        self._create_account(client)
        resp = client.post("/api/rules", json={
            "account_id": 1,
            "name": "Like AI tweets",
            "trigger_type": "keyword",
            "trigger_config": {"keywords": ["AI"]},
            "action_type": "like",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Like AI tweets"
        assert data["trigger_config"]["keywords"] == ["AI"]
        assert data["cooldown_minutes"] == 60

    def test_create_rule_invalid_account(self, client):
        resp = client.post("/api/rules", json={
            "account_id": 999,
            "name": "Bad",
            "trigger_type": "keyword",
            "action_type": "like",
        })
        assert resp.status_code == 400

    def test_list_rules(self, client):
        self._create_account(client)
        client.post("/api/rules", json={
            "account_id": 1, "name": "R1", "trigger_type": "keyword", "action_type": "like",
        })
        resp = client.get("/api/rules")
        assert len(resp.json()) == 1

    def test_toggle_rule(self, client):
        self._create_account(client)
        client.post("/api/rules", json={
            "account_id": 1, "name": "R1", "trigger_type": "keyword", "action_type": "like",
        })
        resp = client.post("/api/rules/1/toggle")
        assert resp.json()["is_active"] is False

        resp = client.post("/api/rules/1/toggle")
        assert resp.json()["is_active"] is True

    def test_update_rule(self, client):
        self._create_account(client)
        client.post("/api/rules", json={
            "account_id": 1, "name": "R1", "trigger_type": "keyword", "action_type": "like",
        })
        resp = client.put("/api/rules/1", json={"daily_limit": 100})
        assert resp.json()["daily_limit"] == 100

    def test_delete_rule(self, client):
        self._create_account(client)
        client.post("/api/rules", json={
            "account_id": 1, "name": "R1", "trigger_type": "keyword", "action_type": "like",
        })
        resp = client.delete("/api/rules/1")
        assert resp.status_code == 204


class TestScheduleEndpoints:
    def _create_account(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })

    def test_create_scheduled_post(self, client):
        self._create_account(client)
        resp = client.post("/api/schedule", json={
            "account_id": 1,
            "content": "Hello scheduled!",
            "scheduled_at": "2025-06-01T12:00:00",
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_list_scheduled_posts(self, client):
        self._create_account(client)
        client.post("/api/schedule", json={
            "account_id": 1, "content": "Post", "scheduled_at": "2025-06-01T12:00:00",
        })
        resp = client.get("/api/schedule")
        assert len(resp.json()) == 1

    def test_delete_scheduled_post(self, client):
        self._create_account(client)
        client.post("/api/schedule", json={
            "account_id": 1, "content": "Post", "scheduled_at": "2025-06-01T12:00:00",
        })
        resp = client.delete("/api/schedule/1")
        assert resp.status_code == 204


class TestMonitorEndpoints:
    def _create_account(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })

    def test_create_monitor(self, client):
        self._create_account(client)
        resp = client.post("/api/monitors", json={
            "account_id": 1,
            "keyword": "AI",
        })
        assert resp.status_code == 201
        assert resp.json()["keyword"] == "AI"

    def test_list_monitors(self, client):
        self._create_account(client)
        client.post("/api/monitors", json={"account_id": 1, "keyword": "AI"})
        resp = client.get("/api/monitors")
        assert len(resp.json()) == 1


class TestLogAndStatsEndpoints:
    def test_list_logs_empty(self, client):
        resp = client.get("/api/logs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_stats_empty(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_accounts"] == 0
        assert data["today_executions"] == 0

    def test_logs_pagination(self, client):
        resp = client.get("/api/logs?limit=10&offset=0")
        assert resp.status_code == 200

    def test_logs_filter(self, client):
        resp = client.get("/api/logs?status=success&action=like")
        assert resp.status_code == 200
