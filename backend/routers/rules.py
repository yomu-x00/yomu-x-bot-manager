"""Rule management API routes (Single Responsibility Principle)."""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_db, get_key
from models import RuleCreate, RuleResponse, RuleUpdate
from repositories import AccountRepository, RuleRepository
from worker import process_rule, run_all_rules

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[RuleResponse])
def list_rules(
    account_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = RuleRepository(conn)
    return repo.list_all(account_id)


@router.post("", response_model=RuleResponse, status_code=201)
def create_rule(
    data: RuleCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    if not AccountRepository(conn).get_by_id(data.account_id):
        raise HTTPException(status_code=400, detail="Account not found")

    repo = RuleRepository(conn)
    return repo.create(
        account_id=data.account_id,
        name=data.name,
        is_active=data.is_active,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
        action_type=data.action_type,
        action_config=data.action_config,
        cooldown_minutes=data.cooldown_minutes,
        daily_limit=data.daily_limit,
    )


@router.post("/run-all")
async def run_all(
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    """アクティブな全ルールを即時実行する。"""
    results = await run_all_rules(conn, key)
    total = sum(results.values())
    return {"executed_total": total, "per_rule": results}


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule(
    rule_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = RuleRepository(conn)
    row = repo.get_by_id(rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return row


@router.put("/{rule_id}", response_model=RuleResponse)
def update_rule(
    rule_id: int,
    data: RuleUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = RuleRepository(conn)
    if not repo.get_by_id(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")

    updates: dict = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.is_active is not None:
        updates["is_active"] = data.is_active
    if data.trigger_type is not None:
        updates["trigger_type"] = data.trigger_type
    if data.trigger_config is not None:
        updates["trigger_config"] = json.dumps(data.trigger_config)
    if data.action_type is not None:
        updates["action_type"] = data.action_type
    if data.action_config is not None:
        updates["action_config"] = json.dumps(data.action_config)
    if data.cooldown_minutes is not None:
        updates["cooldown_minutes"] = data.cooldown_minutes
    if data.daily_limit is not None:
        updates["daily_limit"] = data.daily_limit

    if not updates:
        return repo.get_by_id(rule_id)

    return repo.update(rule_id, updates)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = RuleRepository(conn)
    if repo.delete(rule_id) == 0:
        raise HTTPException(status_code=404, detail="Rule not found")


@router.post("/{rule_id}/toggle", response_model=RuleResponse)
def toggle_rule(
    rule_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = RuleRepository(conn)
    existing = repo.get_by_id(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    return repo.toggle_active(rule_id, existing["is_active"])


@router.post("/{rule_id}/run")
async def run_rule(
    rule_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    repo = RuleRepository(conn)
    row = repo.get_raw_by_id(rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    count = await process_rule(conn, row, key)
    return {"executed": count}
