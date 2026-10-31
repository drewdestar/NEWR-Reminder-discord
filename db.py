"""SQLite persistence for NEWR Reminder. No secrets are stored here.

Same pattern as newr-support/db.py: DB_PATH env var or data.db next
to this file, sqlite3 with Row factory, CREATE TABLE IF NOT EXISTS.

Tables (spec columns, plus two small extras marked below):
  reminders:
    id, user_id, guild_id, channel_id (NULL for DM reminders),
    message, due_at (UTC ISO), created_at (UTC ISO), done (0/1),
    dm (extra, 0/1: deliver by DM instead of to a channel)
  scheduled_announcements:
    id, user_id, guild_id, channel_id, message, due_at (UTC ISO),
    created_at (UTC ISO), done (0/1),
    ping_role_id (extra, NULL when no role ping was requested)
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS reminders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            guild_id INTEGER, channel_id INTEGER, message TEXT,
            due_at TEXT, created_at TEXT, done INTEGER DEFAULT 0,
            dm INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS scheduled_announcements(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            guild_id INTEGER, channel_id INTEGER, message TEXT,
            due_at TEXT, created_at TEXT, done INTEGER DEFAULT 0,
            ping_role_id INTEGER);
        """)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_reminder(user_id: int, guild_id: int | None, channel_id: int | None,
                 message: str, due_at: datetime, dm: bool = False) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message,"
            " due_at, created_at, done, dm) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (user_id, guild_id, channel_id, message,
             due_at.astimezone(timezone.utc).isoformat(), now_iso(), int(dm)))
        return cur.lastrowid


def add_schedule(user_id: int, guild_id: int | None, channel_id: int,
                 message: str, due_at: datetime,
                 ping_role_id: int | None = None) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO scheduled_announcements (user_id, guild_id, channel_id,"
            " message, due_at, created_at, done, ping_role_id)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (user_id, guild_id, channel_id, message,
             due_at.astimezone(timezone.utc).isoformat(), now_iso(), ping_role_id))
        return cur.lastrowid


def list_pending_reminders(user_id: int, guild_id: int | None):
    with _conn() as conn:
        if guild_id is None:
            return conn.execute(
                "SELECT * FROM reminders WHERE user_id=? AND done=0"
                " ORDER BY due_at ASC", (user_id,)).fetchall()
        return conn.execute(
            "SELECT * FROM reminders WHERE user_id=? AND guild_id=? AND done=0"
            " ORDER BY due_at ASC", (user_id, guild_id)).fetchall()


def list_pending_schedules(guild_id: int | None):
    with _conn() as conn:
        if guild_id is None:
            return conn.execute(
                "SELECT * FROM scheduled_announcements WHERE done=0"
                " ORDER BY due_at ASC").fetchall()
        return conn.execute(
            "SELECT * FROM scheduled_announcements WHERE guild_id=? AND done=0"
            " ORDER BY due_at ASC", (guild_id,)).fetchall()


def cancel_reminder(reminder_id: int, user_id: int, staff: bool = False) -> bool:
    """Cancel a pending reminder owned by user_id (or any, if staff)."""
    with _conn() as conn:
        if staff:
            cur = conn.execute(
                "UPDATE reminders SET done=1 WHERE id=? AND done=0", (reminder_id,))
        else:
            cur = conn.execute(
                "UPDATE reminders SET done=1 WHERE id=? AND user_id=? AND done=0",
                (reminder_id, user_id))
        return cur.rowcount > 0


def cancel_schedule(schedule_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE scheduled_announcements SET done=1 WHERE id=? AND done=0",
            (schedule_id,))
        return cur.rowcount > 0


def due_items(table: str):
    """All not-yet-done rows whose due_at is now or in the past."""
    assert table in ("reminders", "scheduled_announcements")
    with _conn() as conn:
        return conn.execute(
            f"SELECT * FROM {table} WHERE done=0 AND due_at <= ?"
            " ORDER BY due_at ASC", (now_iso(),)).fetchall()


def mark_done(table: str, row_id: int) -> None:
    assert table in ("reminders", "scheduled_announcements")
    with _conn() as conn:
        conn.execute(f"UPDATE {table} SET done=1 WHERE id=?", (row_id,))
