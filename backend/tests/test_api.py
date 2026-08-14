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


class TestAppFactory:
    """Verify that create_app() produces a correctly configured application."""

    def test_all_api_routes_registered(self, client):
        routes = {r.path for r in client.app.routes}
        expected = {
            "/api/health",
            "/api/accounts",
            "/api/accounts/{account_id}",
            "/api/accounts/{account_id}/tweet",
            "/api/accounts/{account_id}/timeline",
            "/api/accounts/{account_id}/verify",
            "/api/rules",
            "/api/rules/run-all",
            "/api/rules/{rule_id}",
            "/api/rules/{rule_id}/toggle",
            "/api/rules/{rule_id}/run",
            "/api/schedule",
            "/api/schedule/{post_id}",
            "/api/monitors",
            "/api/monitors/{monitor_id}",
            "/api/monitors/{monitor_id}/toggle",
            "/api/search",
            "/api/uploads",
            "/api/uploads/{filename}",
            "/api/webhook/tweet",
            "/api/logs",
            "/api/stats",
        }
        assert expected.issubset(routes)

    def test_cors_middleware_present(self, client):
        # CORS middleware is present when Allow-Origin header is returned.
        resp = client.get("/api/accounts", headers={"Origin": "http://example.com"})
        assert resp.headers.get("access-control-allow-origin") == "*"


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

    def test_get_account_by_id(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })
        resp = client.get("/api/accounts/1")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_get_account_not_found(self, client):
        resp = client.get("/api/accounts/999")
        assert resp.status_code == 404

    def test_post_tweet_direct(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })
        with patch("routers.accounts.post_tweet", new_callable=AsyncMock) as mock_tweet:
            from executor import ExecutionResult
            mock_tweet.return_value = ExecutionResult(True, '{"id":"1"}', "")
            resp = client.post("/api/accounts/1/tweet", json={"text": "Hello!"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_post_tweet_direct_account_not_found(self, client):
        with patch("routers.accounts.post_tweet", new_callable=AsyncMock):
            resp = client.post("/api/accounts/999/tweet", json={"text": "Hi"})
        assert resp.status_code == 404

    def test_get_account_timeline(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "testbot",
        })
        with patch("routers.accounts.get_user_tweets", new_callable=AsyncMock) as mock_tl:
            from executor import ExecutionResult
            mock_tl.return_value = ExecutionResult(True, '[{"id":"1","text":"hi"}]', "")
            resp = client.get("/api/accounts/1/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testbot"
        assert len(data["tweets"]) == 1


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

    def test_get_rule_by_id(self, client):
        self._create_account(client)
        client.post("/api/rules", json={
            "account_id": 1, "name": "R1", "trigger_type": "keyword", "action_type": "like",
        })
        resp = client.get("/api/rules/1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "R1"

    def test_get_rule_not_found(self, client):
        resp = client.get("/api/rules/999")
        assert resp.status_code == 404

    def test_run_all_rules(self, client):
        self._create_account(client)
        client.post("/api/rules", json={
            "account_id": 1, "name": "R1", "trigger_type": "keyword",
            "trigger_config": {"keywords": ["AI"]}, "action_type": "like",
        })
        with patch("routers.rules.run_all_rules", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {1: 3}
            resp = client.post("/api/rules/run-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["executed_total"] == 3
        assert "1" in data["per_rule"]


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

    def test_delete_posted_bluesky_scheduled_post_deletes_remote_post(self, client):
        client.post("/api/accounts", json={
            "name": "Bluesky Bot", "auth_token": "identifier", "ct0": "app-password",
            "username": "bot.bsky.social", "platform": "bluesky",
        })
        client.post("/api/schedule", json={
            "account_id": 1, "content": "Post", "scheduled_at": "2025-06-01T12:00:00",
        })
        from db import get_connection
        from dependencies import get_db_path
        conn = get_connection(get_db_path())
        conn.execute("UPDATE scheduled_posts SET status='posted', posted_uri=? WHERE id=1", ("at://did:plc:test/app.bsky.feed.post/abc",))
        conn.commit()
        conn.close()

        with patch("routers.schedule.delete_bluesky_post", new_callable=AsyncMock) as mock_delete:
            from bluesky_executor import BlueskyResult
            mock_delete.return_value = BlueskyResult(True, "", "")
            resp = client.delete("/api/schedule/1")
        assert resp.status_code == 204
        mock_delete.assert_awaited_once_with("identifier", "app-password", "at://did:plc:test/app.bsky.feed.post/abc")
        assert client.get("/api/schedule/1").status_code == 404

    def test_get_scheduled_post_by_id(self, client):
        self._create_account(client)
        client.post("/api/schedule", json={
            "account_id": 1, "content": "Hello", "scheduled_at": "2025-06-01T12:00:00",
        })
        resp = client.get("/api/schedule/1")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Hello"

    def test_get_scheduled_post_not_found(self, client):
        resp = client.get("/api/schedule/999")
        assert resp.status_code == 404

    def test_patch_scheduled_post(self, client):
        self._create_account(client)
        client.post("/api/schedule", json={
            "account_id": 1, "content": "Original", "scheduled_at": "2025-06-01T12:00:00",
        })
        resp = client.patch("/api/schedule/1", json={"content": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "Updated"

    def test_patch_posted_returns_409(self, client):
        from db import get_connection
        from dependencies import get_db_path
        self._create_account(client)
        client.post("/api/schedule", json={
            "account_id": 1, "content": "Post", "scheduled_at": "2025-06-01T12:00:00",
        })
        conn = get_connection(get_db_path())
        conn.execute("UPDATE scheduled_posts SET status='posted' WHERE id=1")
        conn.commit()
        conn.close()
        resp = client.patch("/api/schedule/1", json={"content": "Too late"})
        assert resp.status_code == 409


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

    def test_get_monitor_by_id(self, client):
        self._create_account(client)
        client.post("/api/monitors", json={"account_id": 1, "keyword": "AI"})
        resp = client.get("/api/monitors/1")
        assert resp.status_code == 200
        assert resp.json()["keyword"] == "AI"

    def test_get_monitor_not_found(self, client):
        resp = client.get("/api/monitors/999")
        assert resp.status_code == 404

    def test_update_monitor(self, client):
        self._create_account(client)
        client.post("/api/monitors", json={"account_id": 1, "keyword": "AI"})
        resp = client.put("/api/monitors/1", json={"keyword": "ML"})
        assert resp.status_code == 200
        assert resp.json()["keyword"] == "ML"

    def test_update_monitor_not_found(self, client):
        resp = client.put("/api/monitors/999", json={"keyword": "x"})
        assert resp.status_code == 404

    def test_delete_monitor(self, client):
        self._create_account(client)
        client.post("/api/monitors", json={"account_id": 1, "keyword": "AI"})
        resp = client.delete("/api/monitors/1")
        assert resp.status_code == 204
        assert client.get("/api/monitors/1").status_code == 404

    def test_delete_monitor_not_found(self, client):
        resp = client.delete("/api/monitors/999")
        assert resp.status_code == 404

    def test_toggle_monitor(self, client):
        self._create_account(client)
        client.post("/api/monitors", json={"account_id": 1, "keyword": "AI"})
        resp = client.post("/api/monitors/1/toggle")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        resp = client.post("/api/monitors/1/toggle")
        assert resp.json()["is_active"] is True


class TestSearchEndpoints:
    def _create_account(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })

    def test_search_returns_tweets(self, client):
        self._create_account(client)
        with patch("routers.search.search_tweets", new_callable=AsyncMock) as mock_search:
            from executor import ExecutionResult
            mock_search.return_value = ExecutionResult(
                True, '[{"id":"1","text":"AI is great"}]', ""
            )
            resp = client.get("/api/search?account_id=1&q=AI")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "AI"
        assert data["count"] == 1
        assert data["tweets"][0]["text"] == "AI is great"

    def test_search_account_not_found(self, client):
        resp = client.get("/api/search?account_id=999&q=AI")
        assert resp.status_code == 404

    def test_search_with_count_param(self, client):
        self._create_account(client)
        with patch("routers.search.search_tweets", new_callable=AsyncMock) as mock_search:
            from executor import ExecutionResult
            mock_search.return_value = ExecutionResult(True, "[]", "")
            client.get("/api/search?account_id=1&q=test&count=50")
        mock_search.assert_called_once()
        _, call_kwargs = mock_search.call_args
        assert mock_search.call_args[0][3] == 50

    def test_search_cli_error_returns_500(self, client):
        self._create_account(client)
        with patch("routers.search.search_tweets", new_callable=AsyncMock) as mock_search:
            from executor import ExecutionResult
            mock_search.return_value = ExecutionResult(False, "", "rate limit exceeded")
            resp = client.get("/api/search?account_id=1&q=fail")
        assert resp.status_code == 500


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"
        assert "version" in data


class TestUploadsEndpoints:
    def test_list_uploads_empty(self, client):
        resp = client.get("/api/uploads")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["files"] == []

    def test_upload_and_list(self, client):
        import io
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        resp = client.post(
            "/api/uploads",
            files={"file": ("test.png", io.BytesIO(content), "image/png")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"].endswith(".png")
        assert data["size"] == len(content)

        resp = client.get("/api/uploads")
        assert resp.json()["total"] == 1

    def test_upload_unsupported_extension(self, client):
        import io
        resp = client.post(
            "/api/uploads",
            files={"file": ("script.exe", io.BytesIO(b"data"), "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_delete_upload(self, client):
        import io
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        upload_resp = client.post(
            "/api/uploads",
            files={"file": ("del.png", io.BytesIO(content), "image/png")},
        )
        filename = upload_resp.json()["filename"]
        resp = client.delete(f"/api/uploads/{filename}")
        assert resp.status_code == 204

        resp = client.get("/api/uploads")
        assert resp.json()["total"] == 0

    def test_delete_not_found(self, client):
        resp = client.delete("/api/uploads/nonexistent.png")
        assert resp.status_code == 404


class TestWebhookEndpoints:
    def _create_account(self, client):
        client.post("/api/accounts", json={
            "name": "Bot", "auth_token": "t", "ct0": "c", "username": "u",
        })

    def test_webhook_tweet_success(self, client):
        self._create_account(client)
        with patch("routers.webhooks.post_tweet", new_callable=AsyncMock) as mock_tweet:
            from executor import ExecutionResult
            mock_tweet.return_value = ExecutionResult(True, '{"id":"99"}', "")
            resp = client.post("/api/webhook/tweet", json={
                "account_id": 1,
                "text": "Webhook tweet!",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_webhook_tweet_account_not_found(self, client):
        resp = client.post("/api/webhook/tweet", json={
            "account_id": 999, "text": "Hi"
        })
        assert resp.status_code == 404

    def test_webhook_tweet_invalid_token(self, client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", "correct_secret")
        self._create_account(client)
        resp = client.post("/api/webhook/tweet", json={
            "account_id": 1, "text": "Hi", "token": "wrong_secret"
        })
        assert resp.status_code == 401

    def test_webhook_tweet_valid_token(self, client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", "mysecret")
        self._create_account(client)
        with patch("routers.webhooks.post_tweet", new_callable=AsyncMock) as mock_tweet:
            from executor import ExecutionResult
            mock_tweet.return_value = ExecutionResult(True, "{}", "")
            resp = client.post("/api/webhook/tweet", json={
                "account_id": 1, "text": "Hi", "token": "mysecret"
            })
        assert resp.status_code == 200


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
