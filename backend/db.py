"""Database initialization and connection management."""

import sqlite3
from pathlib import Path

DATABASE_PATH = Path("/app/data/twitter.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    auth_token TEXT NOT NULL,
    ct0 TEXT NOT NULL,
    username TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    interval_minutes INTEGER NOT NULL DEFAULT 5,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    trigger_type TEXT NOT NULL CHECK(trigger_type IN ('keyword', 'user', 'engagement', 'schedule')),
    trigger_config JSON NOT NULL DEFAULT '{}',
    action_type TEXT NOT NULL CHECK(action_type IN ('rt', 'like', 'reply', 'follow', 'unfollow')),
    action_config JSON NOT NULL DEFAULT '{}',
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    daily_limit INTEGER NOT NULL DEFAULT 50,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduled_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    scheduled_at DATETIME NOT NULL,
    repeat_type TEXT NOT NULL DEFAULT 'none' CHECK(repeat_type IN ('none', 'daily', 'weekly', 'custom', 'random_window')),
    repeat_config JSON NOT NULL DEFAULT '{}',
    image_paths TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'posted', 'failed')),
    posted_at DATETIME
);

CREATE TABLE IF NOT EXISTS rule_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    tweet_id TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'skipped')),
    reason TEXT,
    executed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    notify_discord BOOLEAN NOT NULL DEFAULT 0,
    discord_webhook TEXT,
    last_checked_at DATETIME,
    is_active BOOLEAN NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_rules_account_id ON rules(account_id);
CREATE INDEX IF NOT EXISTS idx_rule_logs_rule_id ON rule_logs(rule_id);
CREATE INDEX IF NOT EXISTS idx_rule_logs_executed_at ON rule_logs(executed_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_posts_status ON scheduled_posts(status, scheduled_at);
"""


def get_db_path() -> Path:
    """Return the database path, allowing override for testing."""
    return DATABASE_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Create a new database connection with WAL mode and foreign keys enabled."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database schema."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)

        # migrate: add interval_minutes to accounts if missing
        acct_cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        if "interval_minutes" not in acct_cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN interval_minutes INTEGER NOT NULL DEFAULT 5")

        # migrate: add image_paths to scheduled_posts if missing
        post_cols = [r[1] for r in conn.execute("PRAGMA table_info(scheduled_posts)").fetchall()]
        if "image_paths" not in post_cols:
            conn.execute("ALTER TABLE scheduled_posts ADD COLUMN image_paths TEXT NOT NULL DEFAULT '[]'")

        # migrate: expand repeat_type CHECK to include random_window
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='scheduled_posts'").fetchone()
        if row and "random_window" not in row[0]:
            conn.executescript("""
                DROP TABLE IF EXISTS scheduled_posts_new;
                CREATE TABLE scheduled_posts_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    scheduled_at DATETIME NOT NULL,
                    repeat_type TEXT NOT NULL DEFAULT 'none'
                        CHECK(repeat_type IN ('none', 'daily', 'weekly', 'custom', 'random_window')),
                    repeat_config JSON NOT NULL DEFAULT '{}',
                    image_paths TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'posted', 'failed')),
                    posted_at DATETIME
                );
                INSERT INTO scheduled_posts_new
                    (id, account_id, content, scheduled_at, repeat_type, repeat_config, image_paths, status, posted_at)
                SELECT id, account_id, content, scheduled_at, repeat_type, repeat_config, image_paths, status, posted_at
                FROM scheduled_posts;
                DROP TABLE scheduled_posts;
                ALTER TABLE scheduled_posts_new RENAME TO scheduled_posts;
                CREATE INDEX IF NOT EXISTS idx_scheduled_posts_status
                    ON scheduled_posts(status, scheduled_at);
            """)

        conn.commit()
    finally:
        conn.close()
