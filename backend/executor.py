"""Wrapper around twitter-cli for executing Twitter actions."""

import asyncio
import json
import logging
import shlex
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TWITTER_CLI = "twitter"


@dataclass
class ExecutionResult:
    success: bool
    output: str
    error: str


async def run_cli(args: list[str], env: dict[str, str] | None = None) -> ExecutionResult:
    """Execute a twitter-cli command asynchronously.

    Args:
        args: Command arguments (excluding the base 'twitter' command).
        env: Environment variables (TWITTER_AUTH_TOKEN, TWITTER_CT0).

    Returns:
        ExecutionResult with success status, stdout, and stderr.
    """
    cmd = [TWITTER_CLI] + args
    logger.info("Executing: %s", " ".join(shlex.quote(a) for a in cmd))

    import os
    merged_env = {**os.environ, **(env or {})}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        success = proc.returncode == 0
        if not success:
            logger.warning("Command failed (rc=%d): %s", proc.returncode, stderr_str)

        return ExecutionResult(success=success, output=stdout_str, error=stderr_str)
    except asyncio.TimeoutError:
        logger.error("Command timed out: %s", " ".join(cmd))
        return ExecutionResult(success=False, output="", error="Command timed out")
    except FileNotFoundError:
        logger.error("twitter-cli not found in PATH")
        return ExecutionResult(success=False, output="", error="twitter-cli not found")


def make_auth_env(auth_token: str, ct0: str) -> dict[str, str]:
    """Create environment variables for twitter-cli authentication."""
    return {
        "TWITTER_AUTH_TOKEN": auth_token,
        "TWITTER_CT0": ct0,
    }


async def search_tweets(auth_token: str, ct0: str, query: str, count: int = 20) -> ExecutionResult:
    """Search tweets using twitter-cli."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["search", query, "--max", str(count), "--json"], env=env)


async def get_user_tweets(auth_token: str, ct0: str, username: str, count: int = 20) -> ExecutionResult:
    """Get tweets from a specific user."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["user-posts", username, "--max", str(count), "--json"], env=env)


async def like_tweet(auth_token: str, ct0: str, tweet_id: str) -> ExecutionResult:
    """Like a tweet."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["like", tweet_id], env=env)


async def retweet(auth_token: str, ct0: str, tweet_id: str) -> ExecutionResult:
    """Retweet a tweet."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["retweet", tweet_id], env=env)


async def reply_tweet(auth_token: str, ct0: str, tweet_id: str, text: str) -> ExecutionResult:
    """Reply to a tweet."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["reply", tweet_id, text], env=env)


async def follow_user(auth_token: str, ct0: str, username: str) -> ExecutionResult:
    """Follow a user."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["follow", username], env=env)


async def unfollow_user(auth_token: str, ct0: str, username: str) -> ExecutionResult:
    """Unfollow a user."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["unfollow", username], env=env)


async def post_tweet(auth_token: str, ct0: str, text: str) -> ExecutionResult:
    """Post a new tweet."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["post", text], env=env)


async def verify_credentials(auth_token: str, ct0: str) -> ExecutionResult:
    """Verify that the credentials are valid by fetching the authenticated user."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["whoami"], env=env)
