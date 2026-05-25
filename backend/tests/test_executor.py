"""Tests for twitter-cli executor wrapper."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from executor import (
    run_cli,
    make_auth_env,
    search_tweets,
    like_tweet,
    retweet,
    post_tweet,
    verify_credentials,
    ExecutionResult,
)


def test_make_auth_env():
    env = make_auth_env("tok123", "ct0_abc")
    assert env["TWITTER_AUTH_TOKEN"] == "tok123"
    assert env["TWITTER_CT0"] == "ct0_abc"


@pytest.mark.asyncio
async def test_run_cli_success():
    """Successful CLI execution should return success=True."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"output data", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await run_cli(["whoami"])

    assert result.success is True
    assert result.output == "output data"
    assert result.error == ""


@pytest.mark.asyncio
async def test_run_cli_failure():
    """Failed CLI execution should return success=False."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"error msg")
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await run_cli(["bad-command"])

    assert result.success is False
    assert result.error == "error msg"


@pytest.mark.asyncio
async def test_run_cli_not_found():
    """Missing twitter-cli should return a descriptive error."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError,
    ):
        result = await run_cli(["whoami"])

    assert result.success is False
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_run_cli_timeout():
    """Command timeout should be handled gracefully."""
    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await run_cli(["slow-command"])

    assert result.success is False
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_search_tweets():
    """search_tweets should call CLI with correct args including -t Latest."""
    with patch("executor.run_cli", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ExecutionResult(True, "[]", "")
        await search_tweets("tok", "ct0", "AI", count=10)
        mock_run.assert_called_once_with(
            ["search", "AI", "-t", "Latest", "--max", "10", "--json"],
            env={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct0"},
        )


@pytest.mark.asyncio
async def test_like_tweet():
    with patch("executor.run_cli", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ExecutionResult(True, "", "")
        await like_tweet("tok", "ct0", "12345")
        mock_run.assert_called_once_with(
            ["like", "12345", "--json"],
            env={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct0"},
        )


@pytest.mark.asyncio
async def test_retweet():
    with patch("executor.run_cli", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ExecutionResult(True, "", "")
        await retweet("tok", "ct0", "12345")
        mock_run.assert_called_once_with(
            ["retweet", "12345", "--json"],
            env={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct0"},
        )


@pytest.mark.asyncio
async def test_post_tweet():
    with patch("executor.run_cli", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ExecutionResult(True, "", "")
        await post_tweet("tok", "ct0", "Hello world")
        mock_run.assert_called_once_with(
            ["post", "Hello world", "--json"],
            env={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct0"},
        )


@pytest.mark.asyncio
async def test_post_tweet_with_images():
    with patch("executor.run_cli", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ExecutionResult(True, "", "")
        await post_tweet("tok", "ct0", "Hello", images=["/tmp/a.png", "/tmp/b.png"])
        mock_run.assert_called_once_with(
            ["post", "Hello", "--image", "/tmp/a.png", "--image", "/tmp/b.png", "--json"],
            env={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct0"},
        )


@pytest.mark.asyncio
async def test_verify_credentials():
    with patch("executor.run_cli", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ExecutionResult(True, "testuser", "")
        result = await verify_credentials("tok", "ct0")
        assert result.success is True
        assert result.output == "testuser"
