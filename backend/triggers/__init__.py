"""Trigger handler strategies (Open/Closed + Single Responsibility Principle).

Each concrete TriggerHandler encapsulates one trigger type's tweet-fetching
and matching logic. Adding a new trigger type only requires adding a new
class—no modification of existing code is needed.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol, runtime_checkable

from executor import search_tweets, get_user_tweets

logger = logging.getLogger(__name__)


@runtime_checkable
class TriggerHandler(Protocol):
    """Protocol for trigger handlers (Interface Segregation Principle).

    Each trigger type implements *fetch_tweets* (to obtain candidates) and
    *matches* (to evaluate a single tweet against the trigger config).
    """

    async def fetch_tweets(
        self, auth_token: str, ct0: str, config: dict
    ) -> list[dict]:
        """Fetch candidate tweets for this trigger type."""
        ...  # pragma: no cover

    def matches(self, tweet: dict, config: dict) -> bool:
        """Return True if the tweet satisfies the trigger conditions."""
        ...  # pragma: no cover


class KeywordTriggerHandler:
    """Handles 'keyword' trigger: searches tweets by keywords/hashtags."""

    async def fetch_tweets(
        self, auth_token: str, ct0: str, config: dict
    ) -> list[dict]:
        keywords = config.get("keywords", [])
        hashtags = config.get("hashtags", [])
        query = " OR ".join(keywords + hashtags)
        if not query:
            return []
        result = await search_tweets(auth_token, ct0, query)
        if not result.success:
            return []
        try:
            return json.loads(result.output)
        except json.JSONDecodeError:
            logger.warning("Failed to parse search results for keyword trigger")
            return []

    def matches(self, tweet: dict, config: dict) -> bool:
        text = tweet.get("text", "").lower()
        keywords = [k.lower() for k in config.get("keywords", [])]
        hashtags = [h.lower() for h in config.get("hashtags", [])]
        targets = keywords + hashtags
        if not targets:
            return False
        match_mode = config.get("match", "any")
        if match_mode == "all":
            return all(t in text for t in targets)
        return any(t in text for t in targets)


class UserTriggerHandler:
    """Handles 'user' trigger: fetches recent tweets from specific users."""

    async def fetch_tweets(
        self, auth_token: str, ct0: str, config: dict
    ) -> list[dict]:
        usernames = config.get("usernames", [])
        tweets: list[dict] = []
        for username in usernames:
            result = await get_user_tweets(auth_token, ct0, username)
            if not result.success:
                continue
            try:
                user_tweets: list[dict] = json.loads(result.output)
                if not config.get("include_retweets", True):
                    user_tweets = [t for t in user_tweets if not t.get("is_retweet", False)]
                tweets.extend(user_tweets)
            except json.JSONDecodeError:
                logger.warning("Failed to parse timeline for %s", username)
        return tweets

    def matches(self, tweet: dict, config: dict) -> bool:  # noqa: ARG002
        return True  # User trigger matches all fetched tweets


class EngagementTriggerHandler:
    """Handles 'engagement' trigger: filters by like/RT/reply thresholds."""

    async def fetch_tweets(
        self, auth_token: str, ct0: str, config: dict
    ) -> list[dict]:
        # Engagement trigger relies on tweets fetched by other means;
        # if a search_query is provided in config we use it.
        query = config.get("search_query", "")
        if not query:
            return []
        result = await search_tweets(auth_token, ct0, query)
        if not result.success:
            return []
        try:
            return json.loads(result.output)
        except json.JSONDecodeError:
            return []

    def matches(self, tweet: dict, config: dict) -> bool:
        likes = tweet.get("likes", tweet.get("favorite_count", 0))
        rts = tweet.get("retweets", tweet.get("retweet_count", 0))
        replies = tweet.get("replies", tweet.get("reply_count", 0))
        return (
            likes >= config.get("min_likes", 0)
            and rts >= config.get("min_retweets", 0)
            and replies >= config.get("min_replies", 0)
        )


class ScheduleTriggerHandler:
    """Handles 'schedule' trigger: fires only at configured hours/weekdays."""

    async def fetch_tweets(
        self, auth_token: str, ct0: str, config: dict
    ) -> list[dict]:
        if not self.matches({}, config):
            return []
        query = config.get("search_query", "")
        if not query:
            return []
        result = await search_tweets(auth_token, ct0, query)
        if not result.success:
            return []
        try:
            return json.loads(result.output)
        except json.JSONDecodeError:
            return []

    def matches(self, tweet: dict, config: dict) -> bool:  # noqa: ARG002
        now = datetime.now()
        hours = config.get("hours", [])
        days = config.get("days_of_week", [])
        hour_match = not hours or now.hour in hours
        day_match = not days or now.weekday() in days
        return hour_match and day_match


# Registry mapping trigger_type → handler (Open/Closed: add entries without
# modifying the worker or any existing handler class).
TRIGGER_HANDLERS: dict[str, TriggerHandler] = {
    "keyword": KeywordTriggerHandler(),
    "user": UserTriggerHandler(),
    "engagement": EngagementTriggerHandler(),
    "schedule": ScheduleTriggerHandler(),
}


def get_trigger_handler(trigger_type: str) -> TriggerHandler:
    """Return the handler for the given trigger type.

    Raises:
        KeyError: if the trigger_type is not registered.
    """
    handler = TRIGGER_HANDLERS.get(trigger_type)
    if handler is None:
        raise KeyError(f"Unknown trigger type: {trigger_type!r}")
    return handler
