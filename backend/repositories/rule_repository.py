"""Repository for rule data access (Single Responsibility Principle)."""

import json
import sqlite3
from typing import Any


def _parse_rule_row(row: sqlite3.Row) -> dict[str, Any]:
    """Deserialize JSON fields of a rule row."""
    d = dict(row)
    d["trigger_config"] = json.loads(d["trigger_config"]) if isinstance(d["trigger_config"], str) else d["trigger_config"]
    d["action_config"] = json.loads(d["action_config"]) if isinstance(d["action_config"], str) else d["action_config"]
    return d


class RuleRepository:
    """Encapsulates all database queries related to rules."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self, account_id: int | None = None) -> list[dict[str, Any]]:
        """Return all rules, optionally filtered by account."""
        if account_id:
            cursor = self._conn.execute(
                "SELECT * FROM rules WHERE account_id = ? ORDER BY id", (account_id,)
            )
        else:
            cursor = self._conn.execute("SELECT * FROM rules ORDER BY id")
        return [_parse_rule_row(row) for row in cursor.fetchall()]

    def list_active(self) -> list[sqlite3.Row]:
        """Return all active rules belonging to active accounts (raw rows for worker)."""
        cursor = self._conn.execute(
            """SELECT r.* FROM rules r
            JOIN accounts a ON r.account_id = a.id
            WHERE r.is_active = 1 AND a.is_active = 1"""
        )
        return cursor.fetchall()

    def get_by_id(self, rule_id: int) -> dict[str, Any] | None:
        """Return a single parsed rule row, or None."""
        row = self._conn.execute(
            "SELECT * FROM rules WHERE id = ?", (rule_id,)
        ).fetchone()
        return _parse_rule_row(row) if row else None

    def get_raw_by_id(self, rule_id: int) -> sqlite3.Row | None:
        """Return the raw sqlite3.Row for a rule (used by worker)."""
        return self._conn.execute(
            "SELECT * FROM rules WHERE id = ?", (rule_id,)
        ).fetchone()

    def create(
        self,
        account_id: int,
        name: str,
        is_active: bool,
        trigger_type: str,
        trigger_config: dict,
        action_type: str,
        action_config: dict,
        cooldown_minutes: int,
        daily_limit: int,
    ) -> dict[str, Any]:
        """Insert a new rule and return the created row."""
        cursor = self._conn.execute(
            """INSERT INTO rules
            (account_id, name, is_active, trigger_type, trigger_config,
             action_type, action_config, cooldown_minutes, daily_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id, name, is_active, trigger_type,
                json.dumps(trigger_config), action_type,
                json.dumps(action_config), cooldown_minutes, daily_limit,
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM rules WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _parse_rule_row(row)

    def update(self, rule_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial update and return the updated row."""
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rule_id]
        self._conn.execute(f"UPDATE rules SET {set_clause} WHERE id = ?", values)
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM rules WHERE id = ?", (rule_id,)
        ).fetchone()
        return _parse_rule_row(row)

    def toggle_active(self, rule_id: int, current_state: bool) -> dict[str, Any]:
        """Flip is_active and return the updated row."""
        self._conn.execute(
            "UPDATE rules SET is_active = ? WHERE id = ?", (not current_state, rule_id)
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM rules WHERE id = ?", (rule_id,)
        ).fetchone()
        return _parse_rule_row(row)

    def delete(self, rule_id: int) -> int:
        """Delete a rule and return the number of deleted rows."""
        result = self._conn.execute(
            "DELETE FROM rules WHERE id = ?", (rule_id,)
        )
        self._conn.commit()
        return result.rowcount
