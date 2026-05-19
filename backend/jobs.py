"""Shared APScheduler instance and job synchronization utilities."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def sync_account_jobs() -> None:
    """Sync per-account worker jobs with current account settings in DB."""
    from db import get_connection
    from dependencies import get_db_path
    from worker import run_account_rules
    from crypto import get_encryption_key

    conn = get_connection(get_db_path())
    try:
        accounts = conn.execute(
            "SELECT id, interval_minutes FROM accounts WHERE is_active = 1"
        ).fetchall()
    finally:
        conn.close()

    for job in scheduler.get_jobs():
        if job.id.startswith("worker_job_"):
            scheduler.remove_job(job.id)

    for account in accounts:
        account_id = account["id"]
        interval = max(1, account["interval_minutes"])

        async def _job(aid=account_id):
            try:
                conn = get_connection(get_db_path())
                key = get_encryption_key()
                results = await run_account_rules(conn, aid, key)
                logger.info("Worker for account %d completed: %s", aid, results)
                conn.close()
            except Exception:
                logger.exception("Worker job for account %d failed", aid)

        scheduler.add_job(_job, "interval", minutes=interval, id=f"worker_job_{account_id}")

    logger.info("Synced %d account worker job(s)", len(accounts))
