"""FastAPI application factory (Single Responsibility Principle).

This module's only responsibility is to create the FastAPI application,
register routers, configure middleware, and manage the application lifespan.
All business logic lives in routers/, repositories/, worker.py, and scheduler.py.
"""

from dotenv import load_dotenv
load_dotenv()

import json
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crypto import get_encryption_key
from db import init_db
from dependencies import get_db_path
from routers import (
    accounts_router,
    rules_router,
    schedule_router,
    monitors_router,
    logs_router,
)
from worker import run_all_rules
from scheduler import process_pending_posts

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _worker_job() -> None:
    """Periodic job: run all active rules."""
    try:
        from db import get_connection
        conn = get_connection(get_db_path())
        key = get_encryption_key()
        results = await run_all_rules(conn, key)
        logger.info("Worker completed: %s", results)
        conn.close()
    except Exception:
        logger.exception("Worker job failed")


async def _scheduler_job() -> None:
    """Periodic job: process pending scheduled posts."""
    try:
        from db import get_connection
        conn = get_connection(get_db_path())
        key = get_encryption_key()
        count = await process_pending_posts(conn, key)
        logger.info("Scheduler processed %d posts", count)
        conn.close()
    except Exception:
        logger.exception("Scheduler job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialise DB and start background scheduler."""
    init_db(get_db_path())
    scheduler.add_job(_worker_job, "interval", minutes=5, id="worker")
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

    return application


app = create_app()
