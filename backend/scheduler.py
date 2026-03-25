"""Scheduled post management (Single Responsibility + Dependency Inversion).

Refactored to delegate all DB access to ScheduledPostRepository so this
module only contains scheduling/repeat logic.
"""

import logging
import sqlite3
from datetime import datetime, timedelta

from crypto import decrypt
from executor import post_tweet
from repositories.schedule_repository import ScheduledPostRepository

logger = logging.getLogger(__name__)


async def process_pending_posts(conn: sqlite3.Connection, encryption_key: bytes) -> int:
    """Process all pending scheduled posts that are due.

    Returns the number of posts processed.
    """
    repo = ScheduledPostRepository(conn)
    now = datetime.now().isoformat()
    posts = repo.list_pending_due(now)
    processed = 0

    for post in posts:
        post_id = post["id"]
        try:
            auth_token = decrypt(post["auth_token"], encryption_key)
            ct0 = decrypt(post["ct0"], encryption_key)

            result = await post_tweet(auth_token, ct0, post["content"])

            if result.success:
                repo.mark_posted(post_id, datetime.now().isoformat())
                logger.info("Posted scheduled post %d", post_id)
                _schedule_next_repeat(conn, post)
            else:
                repo.mark_failed(post_id)
                logger.warning("Failed to post scheduled post %d: %s", post_id, result.error)

            processed += 1

        except Exception:
            logger.exception("Error processing scheduled post %d", post_id)
            repo.mark_failed(post_id)

    return processed


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

    if next_time:
        ScheduledPostRepository(conn).schedule_repeat(
            account_id=post["account_id"],
            content=post["content"],
            next_time_iso=next_time.isoformat(),
            repeat_type=post["repeat_type"],
            repeat_config=repeat_config,
        )
        logger.info("Scheduled next repeat for post %d at %s", post["id"], next_time)
