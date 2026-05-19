"""Tests for trigger and action strategy handlers (OCP + SRP).

Verifies that each handler implements the expected protocol, that the
registries return the correct handler for each type, and that the
matching/execution logic is correct.
"""

import pytest
from unittest.mock import AsyncMock, patch

from triggers import (
    KeywordTriggerHandler,
    UserTriggerHandler,
    EngagementTriggerHandler,
    ScheduleTriggerHandler,
    TriggerHandler,
    TRIGGER_HANDLERS,
    get_trigger_handler,
)
from actions import (
    LikeActionHandler,
    RetweetActionHandler,
    ReplyActionHandler,
    FollowActionHandler,
    UnfollowActionHandler,
    ActionHandler,
    ACTION_HANDLERS,
    get_action_handler,
)


# ---------------------------------------------------------------------------
# Trigger handler – protocol conformance
# ---------------------------------------------------------------------------

class TestTriggerHandlerRegistry:
    def test_all_registered_trigger_types(self):
        for t in ("keyword", "user", "engagement", "schedule"):
            assert t in TRIGGER_HANDLERS

    def test_get_trigger_handler_returns_instance(self):
        handler = get_trigger_handler("keyword")
        assert isinstance(handler, KeywordTriggerHandler)

    def test_get_trigger_handler_unknown_raises(self):
        with pytest.raises(KeyError):
            get_trigger_handler("nonexistent")

    def test_all_handlers_implement_protocol(self):
        for handler in TRIGGER_HANDLERS.values():
            assert isinstance(handler, TriggerHandler)


# ---------------------------------------------------------------------------
# KeywordTriggerHandler
# ---------------------------------------------------------------------------

class TestKeywordTriggerHandler:
    handler = KeywordTriggerHandler()

    def test_matches_any(self):
        assert self.handler.matches({"text": "AI is great"}, {"keywords": ["AI"], "match": "any"})

    def test_not_matches_any(self):
        assert not self.handler.matches({"text": "Hello world"}, {"keywords": ["AI"]})

    def test_matches_all(self):
        assert self.handler.matches(
            {"text": "AI and ML together"},
            {"keywords": ["AI", "ML"], "match": "all"},
        )

    def test_not_matches_all_partial(self):
        assert not self.handler.matches(
            {"text": "AI only"},
            {"keywords": ["AI", "ML"], "match": "all"},
        )

    def test_case_insensitive(self):
        assert self.handler.matches({"text": "ai rocks"}, {"keywords": ["AI"]})

    def test_hashtag_match(self):
        assert self.handler.matches({"text": "#ChatGPT demo"}, {"hashtags": ["#ChatGPT"]})

    def test_empty_config_no_match(self):
        assert not self.handler.matches({"text": "anything"}, {})

    @pytest.mark.asyncio
    async def test_fetch_tweets_no_query(self):
        tweets = await self.handler.fetch_tweets("t", "c", {})
        assert tweets == []

    @pytest.mark.asyncio
    async def test_fetch_tweets_calls_search(self):
        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.output = '[{"id": "1", "text": "AI"}]'
        with patch("triggers.search_tweets", return_value=mock_result) as mock_search:
            tweets = await self.handler.fetch_tweets(
                "t", "c", {"keywords": ["AI"]}
            )
        assert len(tweets) == 1
        assert tweets[0]["text"] == "AI"

    @pytest.mark.asyncio
    async def test_fetch_tweets_search_failure_returns_empty(self):
        mock_result = AsyncMock()
        mock_result.success = False
        with patch("triggers.search_tweets", return_value=mock_result):
            tweets = await self.handler.fetch_tweets("t", "c", {"keywords": ["AI"]})
        assert tweets == []


# ---------------------------------------------------------------------------
# UserTriggerHandler
# ---------------------------------------------------------------------------

class TestUserTriggerHandler:
    handler = UserTriggerHandler()

    def test_matches_always_true(self):
        assert self.handler.matches({"text": "anything"}, {})

    @pytest.mark.asyncio
    async def test_fetch_tweets_calls_timeline(self):
        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.output = '[{"id": "1", "text": "Hello"}]'
        with patch("triggers.get_user_tweets", return_value=mock_result):
            tweets = await self.handler.fetch_tweets(
                "t", "c", {"usernames": ["testuser"]}
            )
        assert len(tweets) == 1

    @pytest.mark.asyncio
    async def test_fetch_tweets_exclude_retweets(self):
        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.output = '[{"id": "1", "text": "RT ...", "is_retweet": true}, {"id": "2", "text": "Original"}]'
        with patch("triggers.get_user_tweets", return_value=mock_result):
            tweets = await self.handler.fetch_tweets(
                "t", "c", {"usernames": ["u"], "include_retweets": False}
            )
        assert len(tweets) == 1
        assert tweets[0]["id"] == "2"

    @pytest.mark.asyncio
    async def test_fetch_tweets_no_users_returns_empty(self):
        tweets = await self.handler.fetch_tweets("t", "c", {})
        assert tweets == []


# ---------------------------------------------------------------------------
# EngagementTriggerHandler
# ---------------------------------------------------------------------------

class TestEngagementTriggerHandler:
    handler = EngagementTriggerHandler()

    def test_meets_all_thresholds(self):
        tweet = {"likes": 200, "retweets": 100, "replies": 50}
        config = {"min_likes": 100, "min_retweets": 50, "min_replies": 10}
        assert self.handler.matches(tweet, config)

    def test_below_threshold(self):
        tweet = {"likes": 5}
        assert not self.handler.matches(tweet, {"min_likes": 100})

    def test_empty_config_always_matches(self):
        assert self.handler.matches({"likes": 0}, {})

    def test_alternate_field_names(self):
        tweet = {"favorite_count": 200, "retweet_count": 100, "reply_count": 50}
        assert self.handler.matches(tweet, {"min_likes": 100})


# ---------------------------------------------------------------------------
# ScheduleTriggerHandler
# ---------------------------------------------------------------------------

class TestScheduleTriggerHandler:
    handler = ScheduleTriggerHandler()

    def test_matching_hour_and_day(self):
        from datetime import datetime
        now = datetime.now()
        config = {"hours": [now.hour], "days_of_week": [now.weekday()]}
        assert self.handler.matches({}, config)

    def test_non_matching_hour(self):
        from datetime import datetime
        wrong_hour = (datetime.now().hour + 12) % 24
        assert not self.handler.matches({}, {"hours": [wrong_hour]})

    def test_empty_config_always_matches(self):
        assert self.handler.matches({}, {})

    @pytest.mark.asyncio
    async def test_fetch_tweets_when_not_matching_returns_empty(self):
        wrong_hour = (__import__("datetime").datetime.now().hour + 12) % 24
        tweets = await self.handler.fetch_tweets("t", "c", {"hours": [wrong_hour]})
        assert tweets == []

    @pytest.mark.asyncio
    async def test_fetch_tweets_no_query_returns_empty(self):
        tweets = await self.handler.fetch_tweets("t", "c", {})
        assert tweets == []


# ---------------------------------------------------------------------------
# Action handler – protocol conformance
# ---------------------------------------------------------------------------

class TestActionHandlerRegistry:
    def test_all_registered_action_types(self):
        for a in ("like", "rt", "reply", "follow", "unfollow"):
            assert a in ACTION_HANDLERS

    def test_get_action_handler_returns_instance(self):
        handler = get_action_handler("like")
        assert isinstance(handler, LikeActionHandler)

    def test_get_action_handler_unknown_raises(self):
        with pytest.raises(KeyError):
            get_action_handler("nonexistent")

    def test_all_handlers_implement_protocol(self):
        for handler in ACTION_HANDLERS.values():
            assert isinstance(handler, ActionHandler)


# ---------------------------------------------------------------------------
# LikeActionHandler
# ---------------------------------------------------------------------------

class TestLikeActionHandler:
    handler = LikeActionHandler()

    @pytest.mark.asyncio
    async def test_success(self):
        mock_result = AsyncMock()
        mock_result.success = True
        with patch("actions.like_tweet", return_value=mock_result):
            ok, err = await self.handler.execute("t", "c", {}, {"id": "123"})
        assert ok is True
        assert err == ""

    @pytest.mark.asyncio
    async def test_failure(self):
        mock_result = AsyncMock()
        mock_result.success = False
        mock_result.error = "rate limited"
        with patch("actions.like_tweet", return_value=mock_result):
            ok, err = await self.handler.execute("t", "c", {}, {"id": "123"})
        assert ok is False
        assert err == "rate limited"


# ---------------------------------------------------------------------------
# RetweetActionHandler
# ---------------------------------------------------------------------------

class TestRetweetActionHandler:
    handler = RetweetActionHandler()

    @pytest.mark.asyncio
    async def test_success(self):
        mock_result = AsyncMock()
        mock_result.success = True
        with patch("actions.retweet", return_value=mock_result):
            ok, err = await self.handler.execute("t", "c", {}, {"id": "123"})
        assert ok is True


# ---------------------------------------------------------------------------
# ReplyActionHandler
# ---------------------------------------------------------------------------

class TestReplyActionHandler:
    handler = ReplyActionHandler()

    @pytest.mark.asyncio
    async def test_no_reply_text_returns_error(self):
        ok, err = await self.handler.execute("t", "c", {}, {"id": "123"})
        assert ok is False
        assert "reply_text" in err

    @pytest.mark.asyncio
    async def test_success(self):
        mock_result = AsyncMock()
        mock_result.success = True
        with patch("actions.reply_tweet", return_value=mock_result):
            ok, err = await self.handler.execute(
                "t", "c", {"reply_text": "Hello!"}, {"id": "123"}
            )
        assert ok is True


# ---------------------------------------------------------------------------
# FollowActionHandler
# ---------------------------------------------------------------------------

class TestFollowActionHandler:
    handler = FollowActionHandler()

    @pytest.mark.asyncio
    async def test_no_username_returns_error(self):
        ok, err = await self.handler.execute("t", "c", {}, {"text": "no user here"})
        assert ok is False
        assert "username" in err

    @pytest.mark.asyncio
    async def test_success(self):
        mock_result = AsyncMock()
        mock_result.success = True
        with patch("actions.follow_user", return_value=mock_result):
            ok, err = await self.handler.execute(
                "t", "c", {}, {"username": "someuser"}
            )
        assert ok is True

    @pytest.mark.asyncio
    async def test_alternate_field_name(self):
        mock_result = AsyncMock()
        mock_result.success = True
        with patch("actions.follow_user", return_value=mock_result):
            ok, err = await self.handler.execute(
                "t", "c", {}, {"user": {"screen_name": "alt_user"}}
            )
        assert ok is True


# ---------------------------------------------------------------------------
# UnfollowActionHandler
# ---------------------------------------------------------------------------

class TestUnfollowActionHandler:
    handler = UnfollowActionHandler()

    @pytest.mark.asyncio
    async def test_no_username_returns_error(self):
        ok, err = await self.handler.execute("t", "c", {}, {})
        assert ok is False

    @pytest.mark.asyncio
    async def test_success(self):
        mock_result = AsyncMock()
        mock_result.success = True
        with patch("actions.unfollow_user", return_value=mock_result):
            ok, err = await self.handler.execute(
                "t", "c", {}, {"username": "byeuser"}
            )
        assert ok is True
