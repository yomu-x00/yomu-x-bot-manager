"""Account management API routes (Single Responsibility Principle)."""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from crypto import encrypt, decrypt
from dependencies import get_db, get_key
from jobs import sync_account_jobs
from models import AccountCreate, AccountResponse, AccountUpdate, TweetPostRequest
from repositories import AccountRepository
from executor import apply_tweet_suffix, verify_credentials, post_tweet, get_user_tweets, delete_tweet
from bluesky_executor import verify_bluesky, post_bluesky, get_bluesky_posts, delete_bluesky_post

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(conn: sqlite3.Connection = Depends(get_db)):
    repo = AccountRepository(conn)
    return repo.list_all()


@router.get("/cookie-health")
async def cookie_health(
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    """全アカウントの Cookie 有効性を一括チェックする。"""
    repo = AccountRepository(conn)
    accounts = repo.list_all()
    results = []
    for account in accounts:
        row = repo.get_credentials(account["id"])
        token = decrypt(row["auth_token"], key)
        ct0_or_pass = decrypt(row["ct0"], key)
        if account.get("platform") == "bluesky":
            result = await verify_bluesky(token, ct0_or_pass)
        else:
            result = await verify_credentials(token, ct0_or_pass)
        results.append({
            "account_id": account["id"],
            "username": account["username"],
            "platform": account.get("platform", "twitter"),
            "valid": result.success,
            "error": result.error if not result.success else None,
        })
    return results


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
        tweet_suffix=data.tweet_suffix,
        platform=data.platform,
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
    if data.tweet_suffix is not None:
        updates["tweet_suffix"] = data.tweet_suffix or None
    if data.platform is not None:
        updates["platform"] = data.platform

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
    """指定アカウントで即時投稿する（X / Bluesky 対応）。"""
    repo = AccountRepository(conn)
    account_row = repo.get_by_id(account_id)
    if not account_row:
        raise HTTPException(status_code=404, detail="Account not found")

    token = decrypt(account_row["auth_token"], key)
    ct0_or_pass = decrypt(account_row["ct0"], key)
    text = apply_tweet_suffix(data.text, account_row.get("tweet_suffix"))

    if account_row.get("platform") == "bluesky":
        result = await post_bluesky(token, ct0_or_pass, text, data.images)
    else:
        result = await post_tweet(token, ct0_or_pass, text, data.images)

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
    """指定アカウントの最近の投稿一覧を返す（X / Bluesky 対応）。"""
    repo = AccountRepository(conn)
    account = repo.get_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    row = repo.get_credentials(account_id)
    auth_token = decrypt(row["auth_token"], key)
    ct0 = decrypt(row["ct0"], key)
    if account.get("platform") == "bluesky":
        result = await get_bluesky_posts(auth_token, ct0, count)
    else:
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

    token = decrypt(row["auth_token"], key)
    ct0_or_pass = decrypt(row["ct0"], key)
    if row.get("platform") == "bluesky":
        result = await verify_bluesky(token, ct0_or_pass)
    else:
        result = await verify_credentials(token, ct0_or_pass)
    return {"valid": result.success, "output": result.output, "error": result.error}



@router.delete("/{account_id}/tweets/{tweet_id}")
async def delete_account_tweet(
    account_id: int,
    tweet_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    """指定アカウントの投稿を削除する（X / Bluesky 対応）。"""
    repo = AccountRepository(conn)
    row = repo.get_credentials(account_id)
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    auth_token = decrypt(row["auth_token"], key)
    ct0 = decrypt(row["ct0"], key)
    if row.get("platform") == "bluesky":
        result = await delete_bluesky_post(auth_token, ct0, tweet_id)
    else:
        result = await delete_tweet(auth_token, ct0, tweet_id)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"status": "deleted", "tweet_id": tweet_id}
