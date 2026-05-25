"""Account management API routes (Single Responsibility Principle)."""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from crypto import encrypt, decrypt
from dependencies import get_db, get_key
from jobs import sync_account_jobs
from models import AccountCreate, AccountResponse, AccountUpdate, TweetPostRequest
from repositories import AccountRepository
from executor import verify_credentials, post_tweet, get_user_tweets

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(conn: sqlite3.Connection = Depends(get_db)):
    repo = AccountRepository(conn)
    return repo.list_all()


@router.post("", response_model=AccountResponse, status_code=201)
def create_account(
    data: AccountCreate,
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    repo = AccountRepository(conn)
    result = repo.create(
        name=data.name,
        encrypted_token=encrypt(data.auth_token, key),
        encrypted_ct0=encrypt(data.ct0, key),
        username=data.username,
        is_active=data.is_active,
        interval_minutes=data.interval_minutes,
    )
    sync_account_jobs()
    return result


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = AccountRepository(conn)
    row = repo.get_by_id(account_id)
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return row


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    data: AccountUpdate,
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    repo = AccountRepository(conn)
    if not repo.get_by_id(account_id):
        raise HTTPException(status_code=404, detail="Account not found")

    updates: dict = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.username is not None:
        updates["username"] = data.username
    if data.is_active is not None:
        updates["is_active"] = data.is_active
    if data.interval_minutes is not None:
        updates["interval_minutes"] = data.interval_minutes
    if data.auth_token is not None:
        updates["auth_token"] = encrypt(data.auth_token, key)
    if data.ct0 is not None:
        updates["ct0"] = encrypt(data.ct0, key)

    if not updates:
        return repo.get_by_id(account_id)

    result = repo.update(account_id, updates)
    sync_account_jobs()
    return result


@router.delete("/{account_id}", status_code=204)
def delete_account(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    repo = AccountRepository(conn)
    if repo.delete(account_id) == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    sync_account_jobs()


@router.post("/{account_id}/tweet")
async def post_tweet_direct(
    account_id: int,
    data: TweetPostRequest,
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    """指定アカウントで即時ツイートを投稿する。"""
    repo = AccountRepository(conn)
    row = repo.get_credentials(account_id)
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    auth_token = decrypt(row["auth_token"], key)
    ct0 = decrypt(row["ct0"], key)
    result = await post_tweet(auth_token, ct0, data.text, data.images)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    try:
        output = json.loads(result.output)
    except (json.JSONDecodeError, ValueError):
        output = result.output
    return {"status": "ok", "tweet": output}


@router.get("/{account_id}/timeline")
async def get_account_timeline(
    account_id: int,
    count: int = Query(default=20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    """指定アカウントの最近のツイート一覧を返す。"""
    repo = AccountRepository(conn)
    account = repo.get_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    row = repo.get_credentials(account_id)
    auth_token = decrypt(row["auth_token"], key)
    ct0 = decrypt(row["ct0"], key)
    result = await get_user_tweets(auth_token, ct0, account["username"], count)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    try:
        tweets = json.loads(result.output)
    except (json.JSONDecodeError, ValueError):
        tweets = []
    return {"account_id": account_id, "username": account["username"], "tweets": tweets}


@router.post("/{account_id}/verify")
async def verify_account(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    repo = AccountRepository(conn)
    row = repo.get_credentials(account_id)
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    auth_token = decrypt(row["auth_token"], key)
    ct0 = decrypt(row["ct0"], key)
    result = await verify_credentials(auth_token, ct0)
    return {"valid": result.success, "output": result.output, "error": result.error}
