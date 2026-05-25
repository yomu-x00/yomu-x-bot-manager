"""Action handler strategies (Open/Closed + Single Responsibility Principle).

Each concrete ActionHandler encapsulates one action type's execution logic.
Adding a new action type only requires adding a new class and registering it
in ACTION_HANDLERS—no modification of existing code is needed.
"""

import logging
from abc import ABC
from typing import Protocol, runtime_checkable

import httpx

from executor import (
    like_tweet,
    retweet,
    reply_tweet,
    follow_user,
    unfollow_user,
    post_tweet,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class ActionHandler(Protocol):
    """Protocol for action handlers (Interface Segregation Principle).

    Each action type implements *execute*, which performs the action and
    returns ``(success, error_message)``.
    """

    async def execute(
        self,
        auth_token: str,
        ct0: str,
        config: dict,
        tweet: dict,
    ) -> tuple[bool, str]:
        """Execute the action and return (success, error_message)."""
        ...  # pragma: no cover


class LikeActionHandler:
    """Handles 'like' action."""

    async def execute(
        self, auth_token: str, ct0: str, config: dict, tweet: dict
    ) -> tuple[bool, str]:
        tweet_id = str(tweet.get("id", tweet.get("id_str", "")))
        result = await like_tweet(auth_token, ct0, tweet_id)
        return (True, "") if result.success else (False, result.error)


class RetweetActionHandler:
    """Handles 'rt' (retweet) action."""

    async def execute(
        self, auth_token: str, ct0: str, config: dict, tweet: dict
    ) -> tuple[bool, str]:
        tweet_id = str(tweet.get("id", tweet.get("id_str", "")))
        result = await retweet(auth_token, ct0, tweet_id)
        return (True, "") if result.success else (False, result.error)


class ReplyActionHandler:
    """Handles 'reply' action."""

    async def execute(
        self, auth_token: str, ct0: str, config: dict, tweet: dict
    ) -> tuple[bool, str]:
        text = config.get("reply_text", "")
        if not text:
            return False, "reply_text not configured"
        tweet_id = str(tweet.get("id", tweet.get("id_str", "")))
        result = await reply_tweet(auth_token, ct0, tweet_id, text)
        return (True, "") if result.success else (False, result.error)


class FollowActionHandler:
    """Handles 'follow' action."""

    async def execute(
        self, auth_token: str, ct0: str, config: dict, tweet: dict
    ) -> tuple[bool, str]:
        username = tweet.get("username", tweet.get("user", {}).get("screen_name", ""))
        if not username:
            return False, "username not found in tweet"
        result = await follow_user(auth_token, ct0, username)
        return (True, "") if result.success else (False, result.error)


class UnfollowActionHandler:
    """Handles 'unfollow' action."""

    async def execute(
        self, auth_token: str, ct0: str, config: dict, tweet: dict
    ) -> tuple[bool, str]:
        username = tweet.get("username", tweet.get("user", {}).get("screen_name", ""))
        if not username:
            return False, "username not found in tweet"
        result = await unfollow_user(auth_token, ct0, username)
        return (True, "") if result.success else (False, result.error)


class TweetActionHandler:
    """Handles 'tweet' action: posts a new tweet.

    action_config keys:
      text (str): tweet body. Supports {tweet_text}, {tweet_url}, {username} placeholders.
    """

    async def execute(
        self, auth_token: str, ct0: str, config: dict, tweet: dict
    ) -> tuple[bool, str]:
        text = config.get("text", "")
        if not text:
            return False, "text not configured"
        username = tweet.get("username", tweet.get("user", {}).get("screen_name", ""))
        tweet_id = str(tweet.get("id", tweet.get("id_str", "")))
        tweet_url = (
            f"https://twitter.com/{username}/status/{tweet_id}"
            if username and tweet_id
            else ""
        )
        try:
            text = text.format(
                tweet_text=tweet.get("text", ""),
                tweet_url=tweet_url,
                username=username,
            )
        except KeyError:
            pass
        result = await post_tweet(auth_token, ct0, text)
        return (True, "") if result.success else (False, result.error)


class NotifyActionHandler:
    """Handles 'notify' action: POSTs to an external webhook URL.

    action_config keys:
      url (str): destination URL (Discord webhook, Slack, or any HTTP endpoint).
      type (str): "discord" | "webhook" (default "webhook").
      message_template (str): message body with {tweet_text}, {tweet_url}, {username}.
    """

    async def execute(
        self, auth_token: str, ct0: str, config: dict, tweet: dict
    ) -> tuple[bool, str]:
        url = config.get("url", "")
        if not url:
            return False, "notify url not configured"

        notify_type = config.get("type", "webhook")
        template = config.get("message_template", "キーワードを検知しました: {tweet_text}")

        username = tweet.get("username", tweet.get("user", {}).get("screen_name", ""))
        tweet_id = str(tweet.get("id", tweet.get("id_str", "")))
        tweet_url = (
            f"https://twitter.com/{username}/status/{tweet_id}"
            if username and tweet_id
            else ""
        )
        try:
            message = template.format(
                tweet_text=tweet.get("text", ""),
                tweet_url=tweet_url,
                username=username,
            )
        except KeyError:
            message = template

        if notify_type == "discord":
            payload: dict = {"content": message}
        else:
            payload = {"message": message, "tweet_url": tweet_url, "username": username}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code >= 400:
                    return False, f"notify failed: HTTP {resp.status_code}"
        except httpx.RequestError as exc:
            return False, f"notify request failed: {exc}"

        return True, ""


# Registry mapping action_type → handler (Open/Closed: add entries without
# modifying the worker or any existing handler class).
ACTION_HANDLERS: dict[str, ActionHandler] = {
    "like": LikeActionHandler(),
    "rt": RetweetActionHandler(),
    "reply": ReplyActionHandler(),
    "follow": FollowActionHandler(),
    "unfollow": UnfollowActionHandler(),
    "tweet": TweetActionHandler(),
    "notify": NotifyActionHandler(),
}


def get_action_handler(action_type: str) -> ActionHandler:
    """Return the handler for the given action type.

    Raises:
        KeyError: if the action_type is not registered.
    """
    handler = ACTION_HANDLERS.get(action_type)
    if handler is None:
        raise KeyError(f"Unknown action type: {action_type!r}")
    return handler
