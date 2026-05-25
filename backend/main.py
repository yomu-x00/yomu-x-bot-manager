"""FastAPI application factory (Single Responsibility Principle).

This module's only responsibility is to create the FastAPI application,
register routers, configure middleware, and manage the application lifespan.
All business logic lives in routers/, repositories/, worker.py, and scheduler.py.
"""

from dotenv import load_dotenv
load_dotenv()

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from crypto import get_encryption_key
from db import get_connection, init_db
from dependencies import get_db_path
from jobs import scheduler, sync_account_jobs
from routers import (
    accounts_router,
    rules_router,
    schedule_router,
    monitors_router,
    logs_router,
    webhooks_router,
    uploads_router,
    search_router,
)
from scheduler import process_pending_posts

logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


async def _scheduler_job() -> None:
    """Periodic job: process pending scheduled posts."""
    try:
        conn = get_connection(get_db_path())
        key = get_encryption_key()
        count = await process_pending_posts(conn, key)
        logger.info("Scheduler processed %d posts", count)
        conn.close()
    except Exception:
        logger.exception("Scheduler job failed")


def _check_env() -> None:
    """Warn about missing or default environment variables at startup."""
    import sys
    warnings = []

    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key or key == "your_base64_key_here":
        warnings.append(
            "  ENCRYPTION_KEY が未設定です。"
            " `uv run python -c \"from crypto import generate_key; print(generate_key())\"`"
            " で生成して .env に設定してください。"
        )

    db_path = get_db_path()
    if not db_path.parent.exists():
        warnings.append(
            f"  DATABASE_PATH のディレクトリが存在しません: {db_path.parent}"
            " （自動作成します）"
        )

    if warnings:
        print("\n[WARNING] 起動設定を確認してください:", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)
        print("", file=sys.stderr)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialise DB and start background scheduler."""
    _check_env()
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    (db_path.parent / "uploads").mkdir(parents=True, exist_ok=True)
    sync_account_jobs()
    scheduler.add_job(_scheduler_job, "interval", minutes=1, id="scheduler")
    scheduler.start()
    logger.info("Application started")
    yield
    scheduler.shutdown()
    logger.info("Application stopped")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    application = FastAPI(
        title="Twitter Bot Manager",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(accounts_router)
    application.include_router(rules_router)
    application.include_router(schedule_router)
    application.include_router(monitors_router)
    application.include_router(logs_router)
    application.include_router(webhooks_router)
    application.include_router(uploads_router)
    application.include_router(search_router)

    @application.get("/api/health", tags=["system"])
    def health_check():
        """サーバーとDBの死活確認。"""
        db_ok = False
        try:
            conn = get_connection(get_db_path())
            conn.execute("SELECT 1")
            conn.close()
            db_ok = True
        except Exception:
            pass
        return {
            "status": "ok" if db_ok else "degraded",
            "version": "0.1.0",
            "db": "ok" if db_ok else "error",
        }

    # フロントエンド静的ファイル配信（dist/ が存在する場合のみ）
    if FRONTEND_DIST.is_dir():
        application.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @application.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            return FileResponse(FRONTEND_DIST / "index.html")

    return application


app = create_app()
