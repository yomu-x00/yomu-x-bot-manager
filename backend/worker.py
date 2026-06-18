"""Rule engine: evaluates triggers and executes actions.

Refactored to follow SOLID principles:
- SRP: rate-limit helpers delegated to LogRepository
- OCP: trigger/action dispatch uses strategy handlers from triggers/actions modules
- DIP: depends on repository and handler abstractions, not concrete SQL/executor calls

Backward-compatible module-level helpers (get_today_execution_count, check_cooldown,
check_daily_limit, log_execution, matches_*) are preserved for existing callers.
"""

import json
import logging
import sqlite3
from datetime import datetime

from crypto import decrypt
from repositories.log_repository import LogRepository
from triggers import get_trigger_handler
from actions import get_action_handler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backward-compatible helpers (used by existing tests and scheduler)
# ---------------------------------------------------------------------------

def get_today_execution_count(conn: sqlite3.Connection, rule_id: int) -> int:
    """Return the number of successful executions for a rule today."""
    return LogRepository(conn).get_today_success_count(rule_id)


def get_last_execution_time(
    conn: sqlite3.Connection, rule_id: int, tweet_id: str
) -> datetime | None:
    """Return the last successful execution time for a rule-tweet pair."""
    return LogRepository(conn).get_last_execution_time(rule_id, tweet_id)


def check_cooldown(
    conn: sqlite3.Connection, rule_id: int, tweet_id: str, cooldown_minutes: int
) -> bool:
    """Return True if the cooldown period has passed (action is allowed)."""
    last = get_last_execution_time(conn, rule_id, tweet_id)
    if last is None:
        return True
    elapsed = (datetime.now() - last).total_seconds() / 60
    return elapsed >= cooldown_minutes


def check_daily_limit(
    conn: sqlite3.Connection, rule_id: int, daily_limit: int
) -> bool:
    """Return True if the daily execution limit has not been reached."""
    return get_today_execution_count(conn, rule_id) < daily_limit


def log_execution(
    conn: sqlite3.Connection,
    rule_id: int,
    account_id: int,
    tweet_id: str | None,
    action: str,
    status: str,
    reason: str | None = None,
) -> None:
    """Record an execution entry in the rule_logs table."""
    LogRepository(conn).insert(rule_id, account_id, tweet_id, action, status, reason)


# ---------------------------------------------------------------------------
# Trigger-matching helpers kept for backward-compatible test imports
# ---------------------------------------------------------------------------

def matches_keyword_trigger(tweet: dict, config: dict) -> bool:
    """Check if a tweet matches keyword trigger conditions."""
    from triggers import KeywordTriggerHandler
    return KeywordTriggerHandler().matches(tweet, config)


def matches_engagement_trigger(tweet: dict, config: dict) -> bool:
    """Check if a tweet meets engagement thresholds."""
    from triggers import EngagementTriggerHandler
    return EngagementTriggerHandler().matches(tweet, config)


def matches_schedule_trigger(config: dict) -> bool:
    """Check if the current time matches schedule trigger conditions."""
    from triggers import ScheduleTriggerHandler
    return ScheduleTriggerHandler().matches({}, config)


# ---------------------------------------------------------------------------
# Core rule processing (uses strategy pattern via handler registries)
# ---------------------------------------------------------------------------

async def process_rule(
    conn: sqlite3.Connection, rule: sqlite3.Row, encryption_key: bytes
) -> int:
    """Process a single rule: fetch tweets, check conditions, execute actions.

    Returns the number of actions executed.
    """
    rule_id = rule["id"]
    account_id = rule["account_id"]
    trigger_type = rule["trigger_type"]
    trigger_config = (
        json.loads(rule["trigger_config"])
        if isinstance(rule["trigger_config"], str)
        else rule["trigger_config"]
    )
    action_type = rule["action_type"]
    action_config = (
        json.loads(rule["action_config"])
        if isinstance(rule["action_config"], str)
        else rule["action_config"]
    )
    cooldown = rule["cooldown_minutes"]
    daily_limit = rule["daily_limit"]

    # Retrieve active account credentials
    account = conn.execute(
        "SELECT auth_token, ct0, tweet_suffix FROM accounts WHERE id = ? AND is_active = 1",
        (account_id,),
    ).fetchone()
    if not account:
        logger.warning("Account %d not found or inactive for rule %d", account_id, rule_id)
        return 0

    auth_token = decrypt(account["auth_token"], encryption_key)
    ct0 = decrypt(account["ct0"], encryption_key)
    tweet_suffix = account["tweet_suffix"]

    if not check_daily_limit(conn, rule_id, daily_limit):
        logger.info("Rule %d reached daily limit (%d)", rule_id, daily_limit)
        return 0

    # Delegate tweet fetching to the appropriate trigger handler (OCP)
    try:
        trigger_handler = get_trigger_handler(trigger_type)
    except KeyError:
        logger.warning("Unknown trigger type %r for rule %d", trigger_type, rule_id)
        return 0

    tweets = await trigger_handler.fetch_tweets(auth_token, ct0, trigger_config)

    # Delegate action execution to the appropriate action handler (OCP)
    try:
        action_handler = get_action_handler(action_type)
    except KeyError:
        logger.warning("Unknown action type %r for rule %d", action_type, rule_id)
        return 0

    executed = 0
    for tweet in tweets:
        tweet_id = str(tweet.get("id", tweet.get("id_str", "")))
        if not tweet_id:
            continue

        if not check_daily_limit(conn, rule_id, daily_limit):
            break

        if not check_cooldown(conn, rule_id, tweet_id, cooldown):
            log_execution(conn, rule_id, account_id, tweet_id, action_type, "skipped", "cooldown")
            continue

        if not trigger_handler.matches(tweet, trigger_config):
            continue

        config_with_suffix = {**action_config, "_tweet_suffix": tweet_suffix} if action_type == "tweet" else action_config
        success, error = await action_handler.execute(auth_token, ct0, config_with_suffix, tweet)
        if success:
            log_execution(conn, rule_id, account_id, tweet_id, action_type, "success")
            executed += 1
        else:
            log_execution(conn, rule_id, account_id, tweet_id, action_type, "failed", error)

    return executed


async def run_account_rules(
    conn: sqlite3.Connection, account_id: int, encryption_key: bytes
) -> dict[int, int]:
    """Run all active rules for a specific account."""
    cursor = conn.execute(
        """SELECT r.* FROM rules r
        JOIN accounts a ON r.account_id = a.id
        WHERE r.is_active = 1 AND a.is_active = 1 AND r.account_id = ?""",
        (account_id,),
    )
    rules = cursor.fetchall()
    results: dict[int, int] = {}

    for rule in rules:
        try:
            count = await process_rule(conn, rule, encryption_key)
            results[rule["id"]] = count
            logger.info("Rule %d (%s): %d actions executed", rule["id"], rule["name"], count)
        except Exception:
            logger.exception("Error processing rule %d", rule["id"])
            results[rule["id"]] = 0

    return results


async def run_all_rules(conn: sqlite3.Connection, encryption_key: bytes) -> dict[int, int]:
    """Run all active rules and return execution counts per rule."""
    cursor = conn.execute(
        "SELECT id FROM accounts WHERE is_active = 1"
    )
    accounts = cursor.fetchall()
    results = {}

    for account in accounts:
        account_results = await run_account_rules(conn, account["id"], encryption_key)
        results.update(account_results)

    return results
