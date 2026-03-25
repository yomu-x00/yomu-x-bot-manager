"""Rule engine: evaluates triggers and executes actions."""

import json
import logging
import sqlite3
from datetime import datetime, date

from crypto import decrypt
from executor import (
    search_tweets,
    get_user_tweets,
    like_tweet,
    retweet,
    reply_tweet,
    follow_user,
    unfollow_user,
)

logger = logging.getLogger(__name__)


def get_today_execution_count(conn: sqlite3.Connection, rule_id: int) -> int:
    """Get the number of executions for a rule today."""
    today = date.today().isoformat()
    cursor = conn.execute(
        """SELECT COUNT(*) FROM rule_logs
        WHERE rule_id = ? AND status = 'success'
        AND date(executed_at) = ?""",
        (rule_id, today),
    )
    return cursor.fetchone()[0]


def get_last_execution_time(conn: sqlite3.Connection, rule_id: int, tweet_id: str) -> datetime | None:
    """Get the last execution time for a specific rule and tweet."""
    cursor = conn.execute(
        """SELECT executed_at FROM rule_logs
        WHERE rule_id = ? AND tweet_id = ? AND status = 'success'
        ORDER BY executed_at DESC LIMIT 1""",
        (rule_id, tweet_id),
    )
    row = cursor.fetchone()
    if row:
        return datetime.fromisoformat(row[0])
    return None


def check_cooldown(conn: sqlite3.Connection, rule_id: int, tweet_id: str, cooldown_minutes: int) -> bool:
    """Check if the cooldown period has passed for a rule-tweet pair.

    Returns True if action is allowed (cooldown passed or no prior execution).
    """
    last = get_last_execution_time(conn, rule_id, tweet_id)
    if last is None:
        return True
    elapsed = (datetime.now() - last).total_seconds() / 60
    return elapsed >= cooldown_minutes


def check_daily_limit(conn: sqlite3.Connection, rule_id: int, daily_limit: int) -> bool:
    """Check if the daily execution limit has been reached.

    Returns True if action is allowed (under limit).
    """
    count = get_today_execution_count(conn, rule_id)
    return count < daily_limit


def log_execution(
    conn: sqlite3.Connection,
    rule_id: int,
    account_id: int,
    tweet_id: str | None,
    action: str,
    status: str,
    reason: str | None = None,
) -> None:
    """Record an execution in the rule_logs table."""
    conn.execute(
        """INSERT INTO rule_logs (rule_id, account_id, tweet_id, action, status, reason)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (rule_id, account_id, tweet_id, action, status, reason),
    )
    conn.commit()


def matches_keyword_trigger(tweet: dict, config: dict) -> bool:
    """Check if a tweet matches keyword trigger conditions.

    Config format:
        keywords: list of keywords to match
        hashtags: list of hashtags to match
        match: "any" or "all"
    """
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


def matches_engagement_trigger(tweet: dict, config: dict) -> bool:
    """Check if a tweet meets engagement thresholds.

    Config format:
        min_likes: minimum like count
        min_retweets: minimum retweet count
        min_replies: minimum reply count
    """
    likes = tweet.get("likes", tweet.get("favorite_count", 0))
    rts = tweet.get("retweets", tweet.get("retweet_count", 0))
    replies = tweet.get("replies", tweet.get("reply_count", 0))

    min_likes = config.get("min_likes", 0)
    min_rts = config.get("min_retweets", 0)
    min_replies = config.get("min_replies", 0)

    return likes >= min_likes and rts >= min_rts and replies >= min_replies


def matches_schedule_trigger(config: dict) -> bool:
    """Check if the current time matches schedule trigger conditions.

    Config format:
        hours: list of hours (0-23)
        days_of_week: list of weekday numbers (0=Mon, 6=Sun)
    """
    now = datetime.now()
    hours = config.get("hours", [])
    days = config.get("days_of_week", [])

    hour_match = not hours or now.hour in hours
    day_match = not days or now.weekday() in days
    return hour_match and day_match


async def execute_action(
    auth_token: str,
    ct0: str,
    action_type: str,
    action_config: dict,
    tweet: dict,
) -> tuple[bool, str]:
    """Execute the specified action on a tweet.

    Returns (success, error_message).
    """
    tweet_id = tweet.get("id", tweet.get("id_str", ""))

    if action_type == "like":
        result = await like_tweet(auth_token, ct0, str(tweet_id))
    elif action_type == "rt":
        result = await retweet(auth_token, ct0, str(tweet_id))
    elif action_type == "reply":
        text = action_config.get("reply_text", "")
        if not text:
            return False, "reply_text not configured"
        result = await reply_tweet(auth_token, ct0, str(tweet_id), text)
    elif action_type == "follow":
        username = tweet.get("username", tweet.get("user", {}).get("screen_name", ""))
        if not username:
            return False, "username not found in tweet"
        result = await follow_user(auth_token, ct0, username)
    elif action_type == "unfollow":
        username = tweet.get("username", tweet.get("user", {}).get("screen_name", ""))
        if not username:
            return False, "username not found in tweet"
        result = await unfollow_user(auth_token, ct0, username)
    else:
        return False, f"Unknown action type: {action_type}"

    if result.success:
        return True, ""
    return False, result.error


async def process_rule(conn: sqlite3.Connection, rule: sqlite3.Row, encryption_key: bytes) -> int:
    """Process a single rule: fetch tweets, check conditions, execute actions.

    Returns the number of actions executed.
    """
    rule_id = rule["id"]
    account_id = rule["account_id"]
    trigger_type = rule["trigger_type"]
    trigger_config = json.loads(rule["trigger_config"]) if isinstance(rule["trigger_config"], str) else rule["trigger_config"]
    action_type = rule["action_type"]
    action_config = json.loads(rule["action_config"]) if isinstance(rule["action_config"], str) else rule["action_config"]
    cooldown = rule["cooldown_minutes"]
    daily_limit = rule["daily_limit"]

    # Get account credentials
    cursor = conn.execute(
        "SELECT auth_token, ct0 FROM accounts WHERE id = ? AND is_active = 1",
        (account_id,),
    )
    account = cursor.fetchone()
    if not account:
        logger.warning("Account %d not found or inactive for rule %d", account_id, rule_id)
        return 0

    auth_token = decrypt(account["auth_token"], encryption_key)
    ct0 = decrypt(account["ct0"], encryption_key)

    # Check daily limit
    if not check_daily_limit(conn, rule_id, daily_limit):
        logger.info("Rule %d reached daily limit (%d)", rule_id, daily_limit)
        return 0

    # Fetch tweets based on trigger type
    tweets = []

    if trigger_type == "keyword":
        keywords = trigger_config.get("keywords", [])
        hashtags = trigger_config.get("hashtags", [])
        query = " OR ".join(keywords + hashtags)
        if query:
            result = await search_tweets(auth_token, ct0, query)
            if result.success:
                try:
                    tweets = json.loads(result.output)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse search results for rule %d", rule_id)

    elif trigger_type == "user":
        usernames = trigger_config.get("usernames", [])
        for username in usernames:
            result = await get_user_tweets(auth_token, ct0, username)
            if result.success:
                try:
                    user_tweets = json.loads(result.output)
                    if not trigger_config.get("include_retweets", True):
                        user_tweets = [t for t in user_tweets if not t.get("is_retweet", False)]
                    tweets.extend(user_tweets)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse timeline for %s", username)

    elif trigger_type == "schedule":
        if not matches_schedule_trigger(trigger_config):
            return 0
        # For schedule triggers, we still need tweets to act on
        # This is typically combined with keyword or other criteria in action_config
        query = action_config.get("search_query", "")
        if query:
            result = await search_tweets(auth_token, ct0, query)
            if result.success:
                try:
                    tweets = json.loads(result.output)
                except json.JSONDecodeError:
                    pass

    executed = 0
    for tweet in tweets:
        tweet_id = str(tweet.get("id", tweet.get("id_str", "")))
        if not tweet_id:
            continue

        # Check daily limit again (may have been reached during processing)
        if not check_daily_limit(conn, rule_id, daily_limit):
            break

        # Check cooldown
        if not check_cooldown(conn, rule_id, tweet_id, cooldown):
            log_execution(conn, rule_id, account_id, tweet_id, action_type, "skipped", "cooldown")
            continue

        # Check trigger-specific conditions
        if trigger_type == "keyword" and not matches_keyword_trigger(tweet, trigger_config):
            continue
        if trigger_type == "engagement" and not matches_engagement_trigger(tweet, trigger_config):
            continue

        # Execute action
        success, error = await execute_action(auth_token, ct0, action_type, action_config, tweet)
        if success:
            log_execution(conn, rule_id, account_id, tweet_id, action_type, "success")
            executed += 1
        else:
            log_execution(conn, rule_id, account_id, tweet_id, action_type, "failed", error)

    return executed


async def run_all_rules(conn: sqlite3.Connection, encryption_key: bytes) -> dict[int, int]:
    """Run all active rules and return execution counts per rule."""
    cursor = conn.execute(
        """SELECT r.* FROM rules r
        JOIN accounts a ON r.account_id = a.id
        WHERE r.is_active = 1 AND a.is_active = 1"""
    )
    rules = cursor.fetchall()
    results = {}

    for rule in rules:
        try:
            count = await process_rule(conn, rule, encryption_key)
            results[rule["id"]] = count
            logger.info("Rule %d (%s): %d actions executed", rule["id"], rule["name"], count)
        except Exception:
            logger.exception("Error processing rule %d", rule["id"])
            results[rule["id"]] = 0

    return results
