"""Webhook endpoint: receive external triggers and post tweets."""

import logging
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from crypto import decrypt
from dependencies import get_db, get_key
from executor import apply_tweet_suffix, post_tweet
from models import WebhookTweetRequest
from repositories import AccountRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhook", tags=["webhook"])


@router.post("/tweet", status_code=200)
async def webhook_tweet(
    req: WebhookTweetRequest,
    conn: sqlite3.Connection = Depends(get_db),
    key: bytes = Depends(get_key),
):
    """Receive an external webhook and post a tweet.

    Callers inside Docker can use http://twitter-backend:8000/api/webhook/tweet.
    Set WEBHOOK_SECRET in .env to require token authentication.
    """
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if secret and req.token != secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    repo = AccountRepository(conn)
    account_row = repo.get_by_id(req.account_id)
    if not account_row or not account_row.get("is_active"):
        raise HTTPException(status_code=404, detail="Account not found or inactive")

    auth_token = decrypt(account_row["auth_token"], key)
    ct0 = decrypt(account_row["ct0"], key)
    text = apply_tweet_suffix(req.text, account_row.get("tweet_suffix"))

    result = await post_tweet(auth_token, ct0, text, req.images)
    if not result.success:
        logger.warning("webhook_tweet failed for account %d: %s", req.account_id, result.error)
        raise HTTPException(status_code=500, detail=result.error)

    logger.info("webhook_tweet success for account %d", req.account_id)
    return {"status": "ok", "output": result.output}
