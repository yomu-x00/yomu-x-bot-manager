"""Tests for the rule engine worker."""

import json
from datetime import datetime, timedelta

import pytest

from worker import (
    get_today_execution_count,
    check_cooldown,
    check_daily_limit,
    log_execution,
    matches_keyword_trigger,
    matches_engagement_trigger,
    matches_schedule_trigger,
)


class TestMatchesKeywordTrigger:
    def test_any_match(self):
        tweet = {"text": "AI is amazing"}
        config = {"keywords": ["AI", "ML"], "match": "any"}
        assert matches_keyword_trigger(tweet, config) is True

    def test_any_no_match(self):
        tweet = {"text": "Hello world"}
        config = {"keywords": ["AI", "ML"], "match": "any"}
        assert matches_keyword_trigger(tweet, config) is False

    def test_all_match(self):
        tweet = {"text": "AI and ML are great"}
        config = {"keywords": ["AI", "ML"], "match": "all"}
        assert matches_keyword_trigger(tweet, config) is True

    def test_all_partial_match(self):
        tweet = {"text": "AI is great"}
        config = {"keywords": ["AI", "ML"], "match": "all"}
        assert matches_keyword_trigger(tweet, config) is False

    def test_case_insensitive(self):
        tweet = {"text": "ai is cool"}
        config = {"keywords": ["AI"], "match": "any"}
        assert matches_keyword_trigger(tweet, config) is True

    def test_hashtag_match(self):
        tweet = {"text": "Check out #ChatGPT"}
        config = {"hashtags": ["#ChatGPT"], "match": "any"}
        assert matches_keyword_trigger(tweet, config) is True

    def test_empty_config(self):
        tweet = {"text": "anything"}
        config = {}
        assert matches_keyword_trigger(tweet, config) is False

    def test_keywords_and_hashtags(self):
        tweet = {"text": "AI #ChatGPT"}
        config = {"keywords": ["AI"], "hashtags": ["#ChatGPT"], "match": "all"}
        assert matches_keyword_trigger(tweet, config) is True


class TestMatchesEngagementTrigger:
    def test_meets_all_thresholds(self):
        tweet = {"likes": 200, "retweets": 100, "replies": 50}
        config = {"min_likes": 100, "min_retweets": 50, "min_replies": 10}
        assert matches_engagement_trigger(tweet, config) is True

    def test_below_likes(self):
        tweet = {"likes": 50, "retweets": 100, "replies": 50}
        config = {"min_likes": 100}
        assert matches_engagement_trigger(tweet, config) is False

    def test_empty_config(self):
        tweet = {"likes": 0, "retweets": 0, "replies": 0}
        config = {}
        assert matches_engagement_trigger(tweet, config) is True

    def test_alternate_field_names(self):
        tweet = {"favorite_count": 200, "retweet_count": 100, "reply_count": 50}
        config = {"min_likes": 100}
        assert matches_engagement_trigger(tweet, config) is True


class TestMatchesScheduleTrigger:
    def test_matching_hour_and_day(self):
        now = datetime.now()
        config = {"hours": [now.hour], "days_of_week": [now.weekday()]}
        assert matches_schedule_trigger(config) is True

    def test_non_matching_hour(self):
        now = datetime.now()
        wrong_hour = (now.hour + 12) % 24
        config = {"hours": [wrong_hour]}
        assert matches_schedule_trigger(config) is False

    def test_empty_config_always_matches(self):
        config = {}
        assert matches_schedule_trigger(config) is True


class TestDailyLimitAndCooldown:
    def test_get_today_count_zero(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (1, 'rule', 'keyword', 'like')"""
        )
        db_conn.commit()
        assert get_today_execution_count(db_conn, 1) == 0

    def test_get_today_count_with_logs(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (1, 'rule', 'keyword', 'like')"""
        )
        db_conn.execute(
            """INSERT INTO rule_logs (rule_id, account_id, action, status)
            VALUES (1, 1, 'like', 'success')"""
        )
        db_conn.execute(
            """INSERT INTO rule_logs (rule_id, account_id, action, status)
            VALUES (1, 1, 'like', 'failed')"""
        )
        db_conn.commit()
        # Only success counts
        assert get_today_execution_count(db_conn, 1) == 1

    def test_check_daily_limit_under(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (1, 'rule', 'keyword', 'like')"""
        )
        db_conn.commit()
        assert check_daily_limit(db_conn, 1, 50) is True

    def test_check_cooldown_no_prior(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (1, 'rule', 'keyword', 'like')"""
        )
        db_conn.commit()
        assert check_cooldown(db_conn, 1, "tweet123", 60) is True

    def test_log_execution(self, db_conn):
        db_conn.execute(
            "INSERT INTO accounts (name, auth_token, ct0, username) VALUES (?, ?, ?, ?)",
            ("bot", "t", "c", "user"),
        )
        db_conn.execute(
            """INSERT INTO rules (account_id, name, trigger_type, action_type)
            VALUES (1, 'rule', 'keyword', 'like')"""
        )
        db_conn.commit()

        log_execution(db_conn, 1, 1, "tweet123", "like", "success")

        cursor = db_conn.execute("SELECT * FROM rule_logs")
        row = cursor.fetchone()
        assert row["tweet_id"] == "tweet123"
        assert row["status"] == "success"
