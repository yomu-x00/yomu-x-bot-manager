"""Scheduled post management (Single Responsibility + Dependency Inversion).

Refactored to delegate all DB access to ScheduledPostRepository so this
module only contains scheduling/repeat logic.
"""

import json
import logging
import random
import sqlite3
from datetime import datetime, timedelta

from crypto import decrypt
from executor import apply_tweet_suffix, post_tweet
from repositories.schedule_repository import ScheduledPostRepository

logger = logging.getLogger(__name__)


async def post_scheduled_post(repo: ScheduledPostRepository, conn: sqlite3.Connection, post, encryption_key: bytes) -> bool:
    """Post a single scheduled post immediately and update its status.

    Returns True if the post succeeded.
    """
    post_id = post["id"]
    try:
        auth_token = decrypt(post["auth_token"], encryption_key)
        ct0 = decrypt(post["ct0"], encryption_key)

        image_paths = json.loads(post["image_paths"]) if isinstance(post["image_paths"], str) else post["image_paths"]
        content = apply_tweet_suffix(post["content"], post.get("tweet_suffix"))
        result = await post_tweet(auth_token, ct0, content, images=image_paths)

        if result.success:
            repo.mark_posted(post_id, datetime.now().isoformat())
            logger.info("Posted scheduled post %d", post_id)
            _schedule_next_repeat(conn, post)
            return True
        else:
            repo.mark_failed(post_id)
            logger.warning("Failed to post scheduled post %d: %s", post_id, result.error)
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
    now = datetime.now().isoformat()
    posts = repo.list_pending_due(now)

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
