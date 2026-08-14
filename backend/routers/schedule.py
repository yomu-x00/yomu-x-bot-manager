"""Scheduled post management API routes (Single Responsibility Principle)."""

import sqlite3
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_db, get_key
from crypto import decrypt
from bluesky_executor import delete_bluesky_post
from models import (
    BulkImageScheduleRequest,
    ScheduledPostBulkResult,
    ScheduledPostCreate,
    ScheduledPostResponse,
    ScheduledPostUpdate,
)
from repositories import AccountRepository, ScheduledPostRepository
from scheduler import post_scheduled_post

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


@router.post("/bulk", response_model=ScheduledPostBulkResult, status_code=201)
def bulk_create_scheduled_posts(
    posts: list[ScheduledPostCreate],
    conn: sqlite3.Connection = Depends(get_db),
):
    if not posts:
        raise HTTPException(status_code=400, detail="No posts provided")

    account_repo = AccountRepository(conn)
    repo = ScheduledPostRepository(conn)

    created, errors = [], []
    for i, data in enumerate(posts):
        if not account_repo.get_by_id(data.account_id):
            errors.append({"index": i, "reason": f"Account {data.account_id} not found"})
            continue
        try:
            row = repo.create(
                account_id=data.account_id,
                content=data.content,
                scheduled_at=data.scheduled_at.isoformat(),
                repeat_type=data.repeat_type,
                repeat_config=data.repeat_config,
                image_paths=data.image_paths,
            )
            created.append(row)
        except Exception as e:
            errors.append({"index": i, "reason": str(e)})

    return {"created": len(created), "errors": errors}


@router.post("/bulk-images", response_model=ScheduledPostBulkResult, status_code=201)
def bulk_schedule_images(
    data: BulkImageScheduleRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """画像を1枚ずつ、固定キャプション・固定時刻で1日N枚ずつ自動振り分けてスケジュールする。"""
    if not AccountRepository(conn).get_by_id(data.account_id):
        raise HTTPException(status_code=400, detail="Account not found")
    if not data.image_paths:
        raise HTTPException(status_code=400, detail="No images provided")
    if not data.times:
        raise HTTPException(status_code=400, detail="No time slots provided")

    try:
        start = datetime.fromisoformat(data.start_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start_date")

    times = sorted(data.times)
    repo = ScheduledPostRepository(conn)

    created, errors = [], []
    for i, path in enumerate(data.image_paths):
        day_offset = i // len(times)
        slot = i % len(times)
        try:
            hour, minute = map(int, times[slot].split(":"))
        except ValueError:
            errors.append({"index": i, "reason": f"Invalid time slot: {times[slot]}"})
            continue

        scheduled_at = (start + timedelta(days=day_offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        try:
            row = repo.create(
                account_id=data.account_id,
                content=data.caption,
                scheduled_at=scheduled_at.isoformat(),
                repeat_type="none",
                repeat_config={},
                image_paths=[path],
            )
            created.append(row)
        except Exception as e:
            errors.append({"index": i, "reason": str(e)})

    return {"created": len(created), "errors": errors}


@router.post("/{post_id}/retry", response_model=ScheduledPostResponse)
async def retry_post(
    post_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    encryption_key: bytes = Depends(get_key),
):
    """failed状態のスケジュール投稿を再投稿する。"""
    repo = ScheduledPostRepository(conn)
    row = repo.get_with_credentials(post_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    if row["status"] != "failed":
        raise HTTPException(status_code=409, detail="Post is not in failed status")

    success = await post_scheduled_post(repo, conn, row, encryption_key)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to post tweet")

    return repo.get_by_id(post_id)


@router.post("/{post_id}/post-now", response_model=ScheduledPostResponse)
async def post_now(
    post_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    encryption_key: bytes = Depends(get_key),
):
    """指定したスケジュール投稿を即時投稿する。"""
    repo = ScheduledPostRepository(conn)
    row = repo.get_with_credentials(post_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="Only pending posts can be posted")

    success = await post_scheduled_post(repo, conn, row, encryption_key)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to post tweet")

    return repo.get_by_id(post_id)


@router.delete("/{post_id}", status_code=204)
async def delete_scheduled_post(
    post_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    encryption_key: bytes = Depends(get_key),
):
    """予約を削除する。投稿済みの Bluesky 投稿は実投稿も削除する。"""
    repo = ScheduledPostRepository(conn)
    row = repo.get_with_credentials(post_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled post not found")

    if row["status"] == "posted" and row["platform"] == "bluesky":
        posted_uri = row["posted_uri"]
        if not posted_uri:
            raise HTTPException(
                status_code=409,
                detail="This Bluesky post was created before post tracking was enabled. Delete it from Timeline instead.",
            )
        identifier = decrypt(row["auth_token"], encryption_key)
        app_password = decrypt(row["ct0"], encryption_key)
        result = await delete_bluesky_post(identifier, app_password, posted_uri)
        if not result.success:
            raise HTTPException(status_code=502, detail=f"Failed to delete Bluesky post: {result.error}")

    repo.delete(post_id)
