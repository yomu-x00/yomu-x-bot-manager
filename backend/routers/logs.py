"""Execution log and statistics API routes (Single Responsibility Principle)."""

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Query

from dependencies import get_db
from models import RuleLogResponse, StatsResponse
from repositories import AccountRepository, RuleRepository, ScheduledPostRepository, LogRepository

router = APIRouter(tags=["logs"])


@router.get("/api/logs", response_model=list[RuleLogResponse])
def list_logs(
    account_id: int | None = None,
    rule_id: int | None = None,
    action: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = LogRepository(conn)
    return repo.list_logs(
        account_id=account_id,
        rule_id=rule_id,
        action=action,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/api/stats", response_model=StatsResponse)
def get_stats(account_id: int | None = None, conn: sqlite3.Connection = Depends(get_db)):
    today = date.today().isoformat()

    account_repo = AccountRepository(conn)
    rule_repo = RuleRepository(conn)
    post_repo = ScheduledPostRepository(conn)
    log_repo = LogRepository(conn)

    all_accounts = account_repo.list_all()
    all_rules = rule_repo.list_all()
    if account_id:
        all_rules = [r for r in all_rules if r["account_id"] == account_id]
    pending_posts = post_repo.list_all(status="pending")
    if account_id:
        pending_posts = [p for p in pending_posts if p["account_id"] == account_id]
    stats = log_repo.get_today_stats(today, account_id)

    return StatsResponse(
        total_accounts=len(all_accounts),
        active_accounts=sum(1 for a in all_accounts if a["is_active"]),
        total_rules=len(all_rules),
        active_rules=sum(1 for r in all_rules if r["is_active"]),
        pending_posts=len(pending_posts),
        today_executions=sum(stats.values()),
        today_success=stats["success"],
        today_failed=stats["failed"],
        today_skipped=stats["skipped"],
    )
