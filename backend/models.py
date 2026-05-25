"""Pydantic models for request/response validation."""

from datetime import datetime
from pydantic import BaseModel, Field


# --- Account ---

class AccountCreate(BaseModel):
    name: str
    auth_token: str
    ct0: str
    username: str
    is_active: bool = True
    interval_minutes: int = 5


class AccountUpdate(BaseModel):
    name: str | None = None
    auth_token: str | None = None
    ct0: str | None = None
    username: str | None = None
    is_active: bool | None = None
    interval_minutes: int | None = None


class AccountResponse(BaseModel):
    id: int
    name: str
    username: str
    is_active: bool
    interval_minutes: int
    created_at: datetime


# --- Rule ---

class RuleCreate(BaseModel):
    account_id: int
    name: str
    is_active: bool = True
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    action_type: str
    action_config: dict = Field(default_factory=dict)
    cooldown_minutes: int = 60
    daily_limit: int = 50


class RuleUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    trigger_type: str | None = None
    trigger_config: dict | None = None
    action_type: str | None = None
    action_config: dict | None = None
    cooldown_minutes: int | None = None
    daily_limit: int | None = None


class RuleResponse(BaseModel):
    id: int
    account_id: int
    name: str
    is_active: bool
    trigger_type: str
    trigger_config: dict
    action_type: str
    action_config: dict
    cooldown_minutes: int
    daily_limit: int
    created_at: datetime


# --- Scheduled Post ---

class ScheduledPostCreate(BaseModel):
    account_id: int
    content: str
    scheduled_at: datetime
    repeat_type: str = "none"
    repeat_config: dict = Field(default_factory=dict)
    image_paths: list[str] = Field(default_factory=list)


class ScheduledPostUpdate(BaseModel):
    content: str | None = None
    scheduled_at: datetime | None = None


class ScheduledPostResponse(BaseModel):
    id: int
    account_id: int
    content: str
    scheduled_at: datetime
    repeat_type: str
    repeat_config: dict
    image_paths: list[str]
    status: str
    posted_at: datetime | None


# --- Monitor ---

class MonitorCreate(BaseModel):
    account_id: int
    keyword: str
    notify_discord: bool = False
    discord_webhook: str | None = None
    is_active: bool = True


class MonitorUpdate(BaseModel):
    keyword: str | None = None
    notify_discord: bool | None = None
    discord_webhook: str | None = None
    is_active: bool | None = None


class MonitorResponse(BaseModel):
    id: int
    account_id: int
    keyword: str
    notify_discord: bool
    discord_webhook: str | None
    last_checked_at: datetime | None
    is_active: bool


# --- Rule Log ---

class RuleLogResponse(BaseModel):
    id: int
    rule_id: int
    account_id: int
    tweet_id: str | None
    action: str
    status: str
    reason: str | None
    executed_at: datetime


# --- Twitter Direct ---

class TweetPostRequest(BaseModel):
    text: str
    images: list[str] | None = None


# --- Webhook ---

class WebhookTweetRequest(BaseModel):
    account_id: int
    text: str
    token: str | None = None
    images: list[str] | None = None


# --- Stats ---

class StatsResponse(BaseModel):
    total_accounts: int
    active_accounts: int
    total_rules: int
    active_rules: int
    pending_posts: int
    today_executions: int
    today_success: int
    today_failed: int
    today_skipped: int
