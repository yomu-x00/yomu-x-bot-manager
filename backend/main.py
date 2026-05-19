"""FastAPI application entry point with all API endpoints."""

import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from crypto import encrypt, decrypt, get_encryption_key
from db import get_connection, init_db
from models import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    MonitorCreate,
    MonitorResponse,
    RuleCreate,
    RuleLogResponse,
    RuleResponse,
    RuleUpdate,
    ScheduledPostCreate,
    ScheduledPostResponse,
    StatsResponse,
)
from executor import verify_credentials
from worker import run_all_rules, process_rule
from scheduler import process_pending_posts

logger = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get("DATABASE_PATH", "/app/data/twitter.db"))
UPLOAD_DIR = DB_PATH.parent / "uploads"
scheduler = AsyncIOScheduler()


def get_db() -> sqlite3.Connection:
    """Get a database connection."""
    return get_connection(DB_PATH)


async def worker_job():
    """Periodic job: run all active rules."""
    try:
        conn = get_db()
        key = get_encryption_key()
        results = await run_all_rules(conn, key)
        logger.info("Worker completed: %s", results)
        conn.close()
    except Exception:
        logger.exception("Worker job failed")


async def scheduler_job():
    """Periodic job: process pending scheduled posts."""
    try:
        conn = get_db()
        key = get_encryption_key()
        count = await process_pending_posts(conn, key)
        logger.info("Scheduler processed %d posts", count)
        conn.close()
    except Exception:
        logger.exception("Scheduler job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB and start scheduler."""
    init_db(DB_PATH)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    scheduler.add_job(worker_job, "interval", minutes=5, id="worker")
    scheduler.add_job(scheduler_job, "interval", minutes=1, id="scheduler")
    scheduler.start()
    logger.info("Application started")
    yield
    scheduler.shutdown()
    logger.info("Application stopped")


app = FastAPI(title="Twitter Bot Manager", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Account endpoints ---

@app.get("/api/accounts", response_model=list[AccountResponse])
def list_accounts():
    conn = get_db()
    try:
        cursor = conn.execute(
            "SELECT id, name, username, is_active, created_at FROM accounts ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@app.post("/api/accounts", response_model=AccountResponse, status_code=201)
def create_account(data: AccountCreate):
    conn = get_db()
    try:
        key = get_encryption_key()
        encrypted_token = encrypt(data.auth_token, key)
        encrypted_ct0 = encrypt(data.ct0, key)

        cursor = conn.execute(
            """INSERT INTO accounts (name, auth_token, ct0, username, is_active)
            VALUES (?, ?, ?, ?, ?)""",
            (data.name, encrypted_token, encrypted_ct0, data.username, data.is_active),
        )
        conn.commit()
        account_id = cursor.lastrowid

        row = conn.execute(
            "SELECT id, name, username, is_active, created_at FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.put("/api/accounts/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, data: AccountUpdate):
    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Account not found")

        updates = {}
        if data.name is not None:
            updates["name"] = data.name
        if data.username is not None:
            updates["username"] = data.username
        if data.is_active is not None:
            updates["is_active"] = data.is_active
        if data.auth_token is not None:
            key = get_encryption_key()
            updates["auth_token"] = encrypt(data.auth_token, key)
        if data.ct0 is not None:
            key = get_encryption_key()
            updates["ct0"] = encrypt(data.ct0, key)

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [account_id]
            conn.execute(f"UPDATE accounts SET {set_clause} WHERE id = ?", values)
            conn.commit()

        row = conn.execute(
            "SELECT id, name, username, is_active, created_at FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.delete("/api/accounts/{account_id}", status_code=204)
def delete_account(account_id: int):
    conn = get_db()
    try:
        result = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
    finally:
        conn.close()


@app.post("/api/accounts/{account_id}/verify")
async def verify_account(account_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT auth_token, ct0 FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Account not found")

        key = get_encryption_key()
        auth_token = decrypt(row["auth_token"], key)
        ct0 = decrypt(row["ct0"], key)

        result = await verify_credentials(auth_token, ct0)
        return {"valid": result.success, "output": result.output, "error": result.error}
    finally:
        conn.close()


# --- Rule endpoints ---

@app.get("/api/rules", response_model=list[RuleResponse])
def list_rules(account_id: int | None = None):
    conn = get_db()
    try:
        if account_id:
            cursor = conn.execute("SELECT * FROM rules WHERE account_id = ? ORDER BY id", (account_id,))
        else:
            cursor = conn.execute("SELECT * FROM rules ORDER BY id")

        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["trigger_config"] = json.loads(d["trigger_config"]) if isinstance(d["trigger_config"], str) else d["trigger_config"]
            d["action_config"] = json.loads(d["action_config"]) if isinstance(d["action_config"], str) else d["action_config"]
            results.append(d)
        return results
    finally:
        conn.close()


@app.post("/api/rules", response_model=RuleResponse, status_code=201)
def create_rule(data: RuleCreate):
    conn = get_db()
    try:
        account = conn.execute("SELECT id FROM accounts WHERE id = ?", (data.account_id,)).fetchone()
        if not account:
            raise HTTPException(status_code=400, detail="Account not found")

        cursor = conn.execute(
            """INSERT INTO rules (account_id, name, is_active, trigger_type, trigger_config,
            action_type, action_config, cooldown_minutes, daily_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.account_id, data.name, data.is_active, data.trigger_type,
                json.dumps(data.trigger_config), data.action_type,
                json.dumps(data.action_config), data.cooldown_minutes, data.daily_limit,
            ),
        )
        conn.commit()
        rule_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        d = dict(row)
        d["trigger_config"] = json.loads(d["trigger_config"])
        d["action_config"] = json.loads(d["action_config"])
        return d
    finally:
        conn.close()


@app.put("/api/rules/{rule_id}", response_model=RuleResponse)
def update_rule(rule_id: int, data: RuleUpdate):
    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Rule not found")

        updates = {}
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

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [rule_id]
            conn.execute(f"UPDATE rules SET {set_clause} WHERE id = ?", values)
            conn.commit()

        row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        d = dict(row)
        d["trigger_config"] = json.loads(d["trigger_config"])
        d["action_config"] = json.loads(d["action_config"])
        return d
    finally:
        conn.close()


@app.delete("/api/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int):
    conn = get_db()
    try:
        result = conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
    finally:
        conn.close()


@app.post("/api/rules/{rule_id}/toggle", response_model=RuleResponse)
def toggle_rule(rule_id: int):
    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Rule not found")

        new_state = not existing["is_active"]
        conn.execute("UPDATE rules SET is_active = ? WHERE id = ?", (new_state, rule_id))
        conn.commit()

        row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        d = dict(row)
        d["trigger_config"] = json.loads(d["trigger_config"])
        d["action_config"] = json.loads(d["action_config"])
        return d
    finally:
        conn.close()


@app.post("/api/rules/{rule_id}/run")
async def run_rule(rule_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")

        key = get_encryption_key()
        count = await process_rule(conn, row, key)
        return {"executed": count}
    finally:
        conn.close()


# --- Upload endpoint ---

@app.post("/api/uploads")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    filename = f"{uuid.uuid4()}{ext}"
    dest = UPLOAD_DIR / filename
    content = await file.read()
    dest.write_bytes(content)
    return {"path": str(dest)}


# --- Schedule endpoints ---

@app.get("/api/schedule", response_model=list[ScheduledPostResponse])
def list_scheduled_posts(status: str | None = None):
    conn = get_db()
    try:
        if status:
            cursor = conn.execute(
                "SELECT * FROM scheduled_posts WHERE status = ? ORDER BY scheduled_at",
                (status,),
            )
        else:
            cursor = conn.execute("SELECT * FROM scheduled_posts ORDER BY scheduled_at")

        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["repeat_config"] = json.loads(d["repeat_config"]) if isinstance(d["repeat_config"], str) else d["repeat_config"]
            d["image_paths"] = json.loads(d["image_paths"]) if isinstance(d.get("image_paths"), str) else (d.get("image_paths") or [])
            results.append(d)
        return results
    finally:
        conn.close()


@app.post("/api/schedule", response_model=ScheduledPostResponse, status_code=201)
def create_scheduled_post(data: ScheduledPostCreate):
    conn = get_db()
    try:
        account = conn.execute("SELECT id FROM accounts WHERE id = ?", (data.account_id,)).fetchone()
        if not account:
            raise HTTPException(status_code=400, detail="Account not found")

        cursor = conn.execute(
            """INSERT INTO scheduled_posts (account_id, content, scheduled_at, repeat_type, repeat_config, image_paths)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                data.account_id, data.content, data.scheduled_at.isoformat(),
                data.repeat_type, json.dumps(data.repeat_config),
                json.dumps(data.image_paths),
            ),
        )
        conn.commit()
        post_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,)).fetchone()
        d = dict(row)
        d["repeat_config"] = json.loads(d["repeat_config"])
        d["image_paths"] = json.loads(d["image_paths"])
        return d
    finally:
        conn.close()


@app.delete("/api/schedule/{post_id}", status_code=204)
def delete_scheduled_post(post_id: int):
    conn = get_db()
    try:
        result = conn.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Scheduled post not found")
    finally:
        conn.close()


# --- Monitor endpoints ---

@app.get("/api/monitors", response_model=list[MonitorResponse])
def list_monitors():
    conn = get_db()
    try:
        cursor = conn.execute("SELECT * FROM monitors ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@app.post("/api/monitors", response_model=MonitorResponse, status_code=201)
def create_monitor(data: MonitorCreate):
    conn = get_db()
    try:
        account = conn.execute("SELECT id FROM accounts WHERE id = ?", (data.account_id,)).fetchone()
        if not account:
            raise HTTPException(status_code=400, detail="Account not found")

        cursor = conn.execute(
            """INSERT INTO monitors (account_id, keyword, notify_discord, discord_webhook, is_active)
            VALUES (?, ?, ?, ?, ?)""",
            (data.account_id, data.keyword, data.notify_discord, data.discord_webhook, data.is_active),
        )
        conn.commit()
        monitor_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


# --- Log & Stats endpoints ---

@app.get("/api/logs", response_model=list[RuleLogResponse])
def list_logs(
    account_id: int | None = None,
    rule_id: int | None = None,
    action: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    conn = get_db()
    try:
        query = "SELECT * FROM rule_logs WHERE 1=1"
        params: list = []

        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if rule_id:
            query += " AND rule_id = ?"
            params.append(rule_id)
        if action:
            query += " AND action = ?"
            params.append(action)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY executed_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    conn = get_db()
    try:
        today = date.today().isoformat()

        total_accounts = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        active_accounts = conn.execute("SELECT COUNT(*) FROM accounts WHERE is_active = 1").fetchone()[0]
        total_rules = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
        active_rules = conn.execute("SELECT COUNT(*) FROM rules WHERE is_active = 1").fetchone()[0]
        pending_posts = conn.execute("SELECT COUNT(*) FROM scheduled_posts WHERE status = 'pending'").fetchone()[0]

        today_logs = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM rule_logs WHERE date(executed_at) = ? GROUP BY status",
            (today,),
        ).fetchall()

        stats = {"success": 0, "failed": 0, "skipped": 0}
        for row in today_logs:
            stats[row["status"]] = row["cnt"]

        return StatsResponse(
            total_accounts=total_accounts,
            active_accounts=active_accounts,
            total_rules=total_rules,
            active_rules=active_rules,
            pending_posts=pending_posts,
            today_executions=sum(stats.values()),
            today_success=stats["success"],
            today_failed=stats["failed"],
            today_skipped=stats["skipped"],
        )
    finally:
        conn.close()
