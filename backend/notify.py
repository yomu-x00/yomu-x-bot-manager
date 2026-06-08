"""Discord webhook notification utilities."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def send_discord_alert(message: str) -> bool:
    """Send a message to the configured Discord webhook. Returns True on success."""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        logger.debug("DISCORD_WEBHOOK_URL not set, skipping notification")
        return False

    try:
        resp = httpx.post(url, json={"content": message}, timeout=10)
        return resp.status_code in (200, 204)
    except Exception:
        logger.exception("Failed to send Discord notification")
        return False
