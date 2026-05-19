"""Scheduled post management API routes (Single Responsibility Principle)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_db
from models import ScheduledPostCreate, ScheduledPostResponse
from repositories import AccountRepository, ScheduledPostRepository

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("", response_model=list[ScheduledPostResponse])
def list_scheduled_posts(
    status: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = ScheduledPostRepository(conn)
    return repo.list_all(status)


@router.post("", response_model=ScheduledPostResponse, status_code=201)
def create_scheduled_post(
    data: ScheduledPostCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    if not AccountRepository(conn).get_by_id(data.account_id):
        raise HTTPException(status_code=400, detail="Account not found")

    repo = ScheduledPostRepository(conn)
    return repo.create(
        account_id=data.account_id,
        content=data.content,
        scheduled_at=data.scheduled_at.isoformat(),
        repeat_type=data.repeat_type,
        repeat_config=data.repeat_config,
        image_paths=data.image_paths,
    )


@router.delete("/{post_id}", status_code=204)
def delete_scheduled_post(
    post_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = ScheduledPostRepository(conn)
    if repo.delete(post_id) == 0:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
