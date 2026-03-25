"""Scheduled post management and APScheduler integration."""

import json
import logging
import sqlite3
from datetime import datetime, timedelta

from crypto import decrypt
from executor import post_tweet

logger = logging.getLogger(__name__)


async def process_pending_posts(conn: sqlite3.Connection, encryption_key: bytes) -> int:
    """Process all pending scheduled posts that are due.

    Returns the number of posts processed.
    """
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """SELECT sp.*, a.auth_token, a.ct0
        FROM scheduled_posts sp
        JOIN accounts a ON sp.account_id = a.id
        WHERE sp.status = 'pending'
        AND sp.scheduled_at <= ?
        AND a.is_active = 1
        ORDER BY sp.scheduled_at ASC""",
        (now,),
    )
    posts = cursor.fetchall()
    processed = 0

    for post in posts:
        post_id = post["id"]
        try:
            auth_token = decrypt(post["auth_token"], encryption_key)
            ct0 = decrypt(post["ct0"], encryption_key)

            result = await post_tweet(auth_token, ct0, post["content"])

            if result.success:
                conn.execute(
                    "UPDATE scheduled_posts SET status = 'posted', posted_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), post_id),
                )
                logger.info("Posted scheduled post %d", post_id)

                # Handle repeating posts
                _schedule_next_repeat(conn, post)
            else:
                conn.execute(
                    "UPDATE scheduled_posts SET status = 'failed' WHERE id = ?",
                    (post_id,),
                )
                logger.warning("Failed to post scheduled post %d: %s", post_id, result.error)

            conn.commit()
            processed += 1

        except Exception:
            logger.exception("Error processing scheduled post %d", post_id)
            conn.execute(
                "UPDATE scheduled_posts SET status = 'failed' WHERE id = ?",
                (post_id,),
            )
            conn.commit()

    return processed


def _schedule_next_repeat(conn: sqlite3.Connection, post: sqlite3.Row) -> None:
    """Create the next scheduled post for repeating posts."""
    repeat_type = post["repeat_type"]
    if repeat_type == "none":
        return

    scheduled_at = datetime.fromisoformat(post["scheduled_at"])
    repeat_config = json.loads(post["repeat_config"]) if isinstance(post["repeat_config"], str) else post["repeat_config"]

    next_time = None

    if repeat_type == "daily":
        next_time = scheduled_at + timedelta(days=1)

    elif repeat_type == "weekly":
        next_time = scheduled_at + timedelta(weeks=1)

    elif repeat_type == "custom":
        interval_hours = repeat_config.get("interval_hours")
        if interval_hours:
            next_time = scheduled_at + timedelta(hours=interval_hours)

    if next_time:
        conn.execute(
            """INSERT INTO scheduled_posts (account_id, content, scheduled_at, repeat_type, repeat_config, status)
            VALUES (?, ?, ?, ?, ?, 'pending')""",
            (
                post["account_id"],
                post["content"],
                next_time.isoformat(),
                post["repeat_type"],
                json.dumps(repeat_config) if isinstance(repeat_config, dict) else post["repeat_config"],
            ),
        )
        logger.info("Scheduled next repeat for post %d at %s", post["id"], next_time)
