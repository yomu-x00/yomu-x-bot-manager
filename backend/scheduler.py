"""Scheduled post management (Single Responsibility + Dependency Inversion).

Refactored to delegate all DB access to ScheduledPostRepository so this
module only contains scheduling/repeat logic.
"""

import asyncio
import json
import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta

from crypto import decrypt
from executor import apply_tweet_suffix, post_tweet
from bluesky_executor import post_bluesky
from repositories.schedule_repository import ScheduledPostRepository

logger = logging.getLogger(__name__)

# 起動時バッチ投稿防止: この分数より古い pending はスキップ（0 で無効）
STALE_POST_MINUTES = int(os.getenv("STALE_POST_MINUTES", "60"))
# twitter-cli 一時エラー時のリトライ設定
POST_MAX_RETRIES = int(os.getenv("POST_MAX_RETRIES", "3"))
POST_RETRY_DELAY = float(os.getenv("POST_RETRY_DELAY", "10"))


async def post_scheduled_post(repo: ScheduledPostRepository, conn: sqlite3.Connection, post, encryption_key: bytes) -> bool:
    """Post a single scheduled post immediately and update its status.

    Returns True if the post succeeded.
    """
    if not isinstance(post, dict):
        post = dict(post)
    post_id = post["id"]
    try:
        auth_token = decrypt(post["auth_token"], encryption_key)
        ct0 = decrypt(post["ct0"], encryption_key)

        image_paths = json.loads(post["image_paths"]) if isinstance(post["image_paths"], str) else (post["image_paths"] or [])
        content = apply_tweet_suffix(post["content"], post.get("tweet_suffix"))

        # リトライ付き投稿（platform に応じて振り分け）
        platform = post.get("platform", "twitter")
        result = None
        for attempt in range(1, POST_MAX_RETRIES + 1):
            if platform == "bluesky":
                result = await post_bluesky(auth_token, ct0, content, images=image_paths)
            else:
                result = await post_tweet(auth_token, ct0, content, images=image_paths)
            if result.success:
                break
            logger.warning("Post %d attempt %d/%d failed: %s", post_id, attempt, POST_MAX_RETRIES, result.error)
            if attempt < POST_MAX_RETRIES:
                await asyncio.sleep(POST_RETRY_DELAY)

        if result and result.success:
            # Bluesky は返却される AT URI を保存し、Scheduled Posts からも
            # 実際の投稿を削除できるようにする。
            posted_uri = result.output if platform == "bluesky" else None
            repo.mark_posted(post_id, datetime.now().isoformat(), posted_uri)
            logger.info("Posted scheduled post %d", post_id)
            _schedule_next_repeat(conn, post)
            return True
        else:
            repo.mark_failed(post_id)
            logger.warning("Failed to post scheduled post %d after %d attempts: %s", post_id, POST_MAX_RETRIES, result.error if result else "unknown")
            return False

    except Exception:
        logger.exception("Error processing scheduled post %d", post_id)
        repo.mark_failed(post_id)
        return False


async def process_pending_posts(conn: sqlite3.Connection, encryption_key: bytes) -> int:
    """Process all pending scheduled posts that are due.

    Returns the number of posts processed.
    """
    repo = ScheduledPostRepository(conn)
    now = datetime.now()
    posts = repo.list_pending_due(now.isoformat())

    # 古すぎる pending はスキップ（起動時バッチ投稿防止）
    if STALE_POST_MINUTES > 0:
        stale_threshold = now - timedelta(minutes=STALE_POST_MINUTES)
        fresh, stale = [], []
        for post in posts:
            try:
                scheduled = datetime.fromisoformat(post["scheduled_at"])
            except (ValueError, TypeError):
                fresh.append(post)
                continue
            if scheduled < stale_threshold:
                stale.append(post)
            else:
                fresh.append(post)

        if stale:
            logger.warning(
                "Skipping %d stale pending post(s) (older than %d min): ids=%s",
                len(stale), STALE_POST_MINUTES, [p["id"] for p in stale],
            )
            for post in stale:
                repo.mark_failed(post["id"])
        posts = fresh

    for post in posts:
        await post_scheduled_post(repo, conn, post, encryption_key)

    return len(posts)


def _schedule_next_repeat(conn: sqlite3.Connection, post: sqlite3.Row) -> None:
    """Create the next scheduled post for repeating posts."""
    repeat_type = post["repeat_type"]
    if repeat_type == "none":
        return

    import json
    scheduled_at = datetime.fromisoformat(post["scheduled_at"])
    repeat_config = (
        json.loads(post["repeat_config"])
        if isinstance(post["repeat_config"], str)
        else post["repeat_config"]
    )

    next_time: datetime | None = None

    if repeat_type == "daily":
        next_time = scheduled_at + timedelta(days=1)
    elif repeat_type == "weekly":
        next_time = scheduled_at + timedelta(weeks=1)
    elif repeat_type == "custom":
        interval_hours = repeat_config.get("interval_hours")
        if interval_hours:
            next_time = scheduled_at + timedelta(hours=interval_hours)

    elif repeat_type == "random_window":
        window_start = repeat_config.get("window_start", "09:00")
        window_end = repeat_config.get("window_end", "18:00")
        start_h, start_m = map(int, window_start.split(":"))
        end_h, end_m = map(int, window_end.split(":"))
        start_mins = start_h * 60 + start_m
        end_mins = end_h * 60 + end_m

        candidate = scheduled_at + timedelta(days=1)
        days_config = repeat_config.get("days", [])
        if days_config:
            day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
            allowed = {day_map[d] for d in days_config if d in day_map}
            for _ in range(7):
                if candidate.weekday() in allowed:
                    break
                candidate += timedelta(days=1)

        rand_mins = random.randint(start_mins, end_mins)
        next_time = candidate.replace(
            hour=rand_mins // 60, minute=rand_mins % 60, second=0, microsecond=0
        )

    if next_time:
        ScheduledPostRepository(conn).schedule_repeat(
            account_id=post["account_id"],
            content=post["content"],
            next_time_iso=next_time.isoformat(),
            repeat_type=post["repeat_type"],
            repeat_config=repeat_config,
        )
        logger.info("Scheduled next repeat for post %d at %s", post["id"], next_time)
