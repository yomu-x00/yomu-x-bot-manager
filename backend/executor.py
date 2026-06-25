"""Wrapper around twitter-cli for executing Twitter actions."""

import asyncio
import logging
import os
import shlex
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TWITTER_CLI = "twitter"


@dataclass
class ExecutionResult:
    success: bool
    output: str
    error: str


def apply_tweet_suffix(text: str, suffix: str | None) -> str:
    """末尾テキストを付与し、280字を超える場合は本文を切り詰める。"""
    if not suffix:
        return text
    combined = text + suffix
    if len(combined) <= 280:
        return combined
    max_text = 280 - len(suffix)
    if max_text <= 0:
        logger.warning("tweet_suffix alone exceeds 280 chars; suffix not applied")
        return text
    logger.warning("Tweet text truncated by %d chars to fit tweet_suffix", len(text) - max_text)
    return text[:max_text] + suffix


def make_auth_env(auth_token: str, ct0: str) -> dict[str, str]:
    return {
        "TWITTER_AUTH_TOKEN": auth_token,
        "TWITTER_CT0": ct0,
    }


async def run_cli(args: list[str], env: dict[str, str] | None = None) -> ExecutionResult:
    cmd = [TWITTER_CLI] + args
    logger.info("Executing: %s", " ".join(shlex.quote(a) for a in cmd))

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


async def post_tweet(auth_token: str, ct0: str, text: str, images: list[str] | None = None) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    args = ["post", text]
    for path in (images or []):
        args += ["--image", path]
    args.append("--json")
    return await run_cli(args, env=env)


async def like_tweet(auth_token: str, ct0: str, tweet_id: str) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["like", tweet_id, "--json"], env=env)


async def retweet(auth_token: str, ct0: str, tweet_id: str) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["retweet", tweet_id, "--json"], env=env)


async def reply_tweet(auth_token: str, ct0: str, tweet_id: str, text: str) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["reply", tweet_id, text, "--json"], env=env)


async def follow_user(auth_token: str, ct0: str, username: str) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["follow", username, "--json"], env=env)


async def unfollow_user(auth_token: str, ct0: str, username: str) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["unfollow", username, "--json"], env=env)


async def search_tweets(auth_token: str, ct0: str, query: str, count: int = 20) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["search", query, "-t", "Latest", "--max", str(count), "--json"], env=env)


async def get_user_tweets(auth_token: str, ct0: str, username: str, count: int = 20) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["user-posts", username, "--max", str(count), "--json"], env=env)


async def delete_tweet(auth_token: str, ct0: str, tweet_id: str) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["delete", tweet_id, "--yes", "--json"], env=env)


async def verify_credentials(auth_token: str, ct0: str) -> ExecutionResult:
    """Verify that the credentials are valid by fetching the authenticated user."""
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["whoami", "--json"], env=env)


# Twitter bearer token used by the web client (public, hardcoded in Twitter's JS)
_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"


def _twitter_headers(auth_token: str, ct0: str) -> dict:
    return {
        "authorization": f"Bearer {_BEARER}",
        "x-csrf-token": ct0,
        "cookie": f"auth_token={auth_token}; ct0={ct0}",
        "content-type": "application/x-www-form-urlencoded",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
    }


async def pin_tweet(auth_token: str, ct0: str, tweet_id: str) -> ExecutionResult:
    """ツイートをプロフィールに固定する。"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.twitter.com/1.1/account/pin_tweet.json",
                headers=_twitter_headers(auth_token, ct0),
                content=f"tweet_mode=extended&id={tweet_id}",
            )
        if resp.status_code == 200:
            return ExecutionResult(success=True, output=resp.text, error="")
        return ExecutionResult(success=False, output="", error=f"HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        return ExecutionResult(success=False, output="", error=str(e))


async def unpin_tweet(auth_token: str, ct0: str, tweet_id: str) -> ExecutionResult:
    """ツイートの固定を解除する。"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.twitter.com/1.1/account/unpin_tweet.json",
                headers=_twitter_headers(auth_token, ct0),
                content=f"tweet_mode=extended&id={tweet_id}",
            )
        if resp.status_code == 200:
            return ExecutionResult(success=True, output=resp.text, error="")
        return ExecutionResult(success=False, output="", error=f"HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        return ExecutionResult(success=False, output="", error=str(e))
