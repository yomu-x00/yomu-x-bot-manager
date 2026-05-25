"""Monitor management API routes (Single Responsibility Principle)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_db
from models import MonitorCreate, MonitorResponse, MonitorUpdate
from repositories import AccountRepository, MonitorRepository

router = APIRouter(prefix="/api/monitors", tags=["monitors"])


@router.get("", response_model=list[MonitorResponse])
def list_monitors(conn: sqlite3.Connection = Depends(get_db)):
    repo = MonitorRepository(conn)
    return repo.list_all()


@router.post("", response_model=MonitorResponse, status_code=201)
def create_monitor(
    data: MonitorCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    if not AccountRepository(conn).get_by_id(data.account_id):
        raise HTTPException(status_code=400, detail="Account not found")

    repo = MonitorRepository(conn)
    return repo.create(
        account_id=data.account_id,
        keyword=data.keyword,
        notify_discord=data.notify_discord,
        discord_webhook=data.discord_webhook,
        is_active=data.is_active,
    )


@router.get("/{monitor_id}", response_model=MonitorResponse)
def get_monitor(
    monitor_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = MonitorRepository(conn)
    row = repo.get_by_id(monitor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return row


@router.put("/{monitor_id}", response_model=MonitorResponse)
def update_monitor(
    monitor_id: int,
    data: MonitorUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = MonitorRepository(conn)
    if not repo.get_by_id(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")

    updates: dict = {}
    if data.keyword is not None:
        updates["keyword"] = data.keyword
    if data.notify_discord is not None:
        updates["notify_discord"] = data.notify_discord
    if data.discord_webhook is not None:
        updates["discord_webhook"] = data.discord_webhook
    if data.is_active is not None:
        updates["is_active"] = data.is_active
    if not updates:
        return repo.get_by_id(monitor_id)
    return repo.update(monitor_id, updates)


@router.delete("/{monitor_id}", status_code=204)
def delete_monitor(
    monitor_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = MonitorRepository(conn)
    if repo.delete(monitor_id) == 0:
        raise HTTPException(status_code=404, detail="Monitor not found")


@router.post("/{monitor_id}/toggle", response_model=MonitorResponse)
def toggle_monitor(
    monitor_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = MonitorRepository(conn)
    existing = repo.get_by_id(monitor_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return repo.toggle_active(monitor_id, existing["is_active"])
