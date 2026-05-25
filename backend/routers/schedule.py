"""Scheduled post management API routes (Single Responsibility Principle)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_db
from models import ScheduledPostCreate, ScheduledPostResponse, ScheduledPostUpdate
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


@router.get("/{post_id}", response_model=ScheduledPostResponse)
def get_scheduled_post(
    post_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = ScheduledPostRepository(conn)
    row = repo.get_by_id(post_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    return row


@router.patch("/{post_id}", response_model=ScheduledPostResponse)
def update_scheduled_post(
    post_id: int,
    data: ScheduledPostUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = ScheduledPostRepository(conn)
    existing = repo.get_by_id(post_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    if existing.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Only pending posts can be updated")

    updates: dict = {}
    if data.content is not None:
        updates["content"] = data.content
    if data.scheduled_at is not None:
        updates["scheduled_at"] = data.scheduled_at.isoformat()
    if not updates:
        return existing
    return repo.update(post_id, updates)


@router.delete("/{post_id}", status_code=204)
def delete_scheduled_post(
    post_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = ScheduledPostRepository(conn)
    if repo.delete(post_id) == 0:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
