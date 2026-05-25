"""Tweet search API route."""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from crypto import decrypt
from dependencies import get_db, get_key
from executor import search_tweets
from repositories import AccountRepository

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    account_id: int,
    q: str,
    count: int = Query(default=20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    """指定アカウントの認証情報を使って Twitter 検索を実行する。

    ルールのトリガー設定のテストや、キーワード検証に使用できる。
    """
    repo = AccountRepository(conn)
    row = repo.get_credentials(account_id)
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    auth_token = decrypt(row["auth_token"], key)
    ct0 = decrypt(row["ct0"], key)

    result = await search_tweets(auth_token, ct0, q, count)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    try:
        tweets = json.loads(result.output)
    except (json.JSONDecodeError, ValueError):
        tweets = []

    return {"query": q, "count": len(tweets), "tweets": tweets}
