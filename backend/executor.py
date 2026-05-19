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


async def verify_credentials(auth_token: str, ct0: str) -> ExecutionResult:
    env = make_auth_env(auth_token, ct0)
    return await run_cli(["whoami", "--json"], env=env)
