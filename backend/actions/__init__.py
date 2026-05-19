"""Action handler strategies (Open/Closed + Single Responsibility Principle).

Each concrete ActionHandler encapsulates one action type's execution logic.
Adding a new action type only requires adding a new class and registering it
in ACTION_HANDLERS—no modification of existing code is needed.
"""

import logging
from abc import ABC
from typing import Protocol, runtime_checkable

from executor import (
    like_tweet,
    retweet,
    reply_tweet,
    follow_user,
    unfollow_user,
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


# Registry mapping action_type → handler (Open/Closed: add entries without
# modifying the worker or any existing handler class).
ACTION_HANDLERS: dict[str, ActionHandler] = {
    "like": LikeActionHandler(),
    "rt": RetweetActionHandler(),
    "reply": ReplyActionHandler(),
    "follow": FollowActionHandler(),
    "unfollow": UnfollowActionHandler(),
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
