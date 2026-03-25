"""Monitor management API routes (Single Responsibility Principle)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_db
from models import MonitorCreate, MonitorResponse
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
