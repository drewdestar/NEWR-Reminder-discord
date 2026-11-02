"""SQLite persistence for NEWR Reminder. No secrets are stored here.

Same pattern as newr-support/db.py: DB_PATH env var or data.db next
to this file, sqlite3 with Row factory, CREATE TABLE IF NOT EXISTS.

Tables:
  reminders:
    id, user_id, guild_id, channel_id (NULL for DM reminders),
    message, due_at (UTC ISO), created_at (UTC ISO), done (0/1),
    dm (0/1: deliver by DM instead of to a channel),
    target_user_id (NULL unless a staff member targeted another user),
    target_role_id (NULL unless a staff member targeted a role),
    repeat ('none'/'daily'/'weekly'; recurring reminders reschedule
    instead of being marked done),
    source_message_id / source_channel_id (NULL unless created by a
    ⏰ reaction; used to avoid duplicate reaction reminders)
  scheduled_announcements:
    id, user_id, guild_id, channel_id, message, due_at (UTC ISO),
    created_at (UTC ISO), done (0/1),
    ping_role_id (NULL when no role ping was requested),
    repeat ('none'/'daily'/'weekly'),
    event_id (NULL unless created by /schedule_event, holding the
    Discord guild scheduled event id)

init_db() also migrates older databases: any column listed above
that is missing is added with ALTER TABLE, so an existing data.db
keeps working without a rebuild.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data.db"))

_REMINDER_COLUMNS = {
    "target_user_id": "INTEGER",
    "target_role_id": "INTEGER",
    "repeat": "TEXT DEFAULT 'none'",
    "source_message_id": "INTEGER",
    "source_channel_id": "INTEGER",
}
_SCHEDULE_COLUMNS = {
    "repeat": "TEXT DEFAULT 'none'",
    "event_id": "INTEGER",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection, table: str, columns: dict) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db() -> None:
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS reminders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            guild_id INTEGER, channel_id INTEGER, message TEXT,
            due_at TEXT, created_at TEXT, done INTEGER DEFAULT 0,
            dm INTEGER DEFAULT 0, target_user_id INTEGER,
            target_role_id INTEGER, repeat TEXT DEFAULT 'none',
            source_message_id INTEGER, source_channel_id INTEGER);
        CREATE TABLE IF NOT EXISTS scheduled_announcements(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            guild_id INTEGER, channel_id INTEGER, message TEXT,
            due_at TEXT, created_at TEXT, done INTEGER DEFAULT 0,
            ping_role_id INTEGER, repeat TEXT DEFAULT 'none',
            event_id INTEGER);
        """)
        _migrate(conn, "reminders", _REMINDER_COLUMNS)
        _migrate(conn, "scheduled_announcements", _SCHEDULE_COLUMNS)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_repeat(repeat: str | None) -> str:
    return repeat if repeat in ("daily", "weekly") else "none"


def add_reminder(user_id: int, guild_id: int | None, channel_id: int | None,
                 message: str, due_at: datetime, dm: bool = False,
                 target_user_id: int | None = None,
                 target_role_id: int | None = None,
                 repeat: str = "none",
                 source_message_id: int | None = None,
                 source_channel_id: int | None = None) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message,"
            " due_at, created_at, done, dm, target_user_id, target_role_id,"
            " repeat, source_message_id, source_channel_id)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)",
            (user_id, guild_id, channel_id, message,
             due_at.astimezone(timezone.utc).isoformat(), now_iso(), int(dm),
             target_user_id, target_role_id, _clean_repeat(repeat),
             source_message_id, source_channel_id))
        return cur.lastrowid


def add_schedule(user_id: int, guild_id: int | None, channel_id: int,
                 message: str, due_at: datetime,
                 ping_role_id: int | None = None, repeat: str = "none",
                 event_id: int | None = None) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO scheduled_announcements (user_id, guild_id, channel_id,"
            " message, due_at, created_at, done, ping_role_id, repeat, event_id)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (user_id, guild_id, channel_id, message,
             due_at.astimezone(timezone.utc).isoformat(), now_iso(),
             ping_role_id, _clean_repeat(repeat), event_id))
        return cur.lastrowid


def get_reminder(reminder_id: int):
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()


def get_schedule(schedule_id: int):
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM scheduled_announcements WHERE id=?",
            (schedule_id,)).fetchone()


def find_pending_reminder_by_source(user_id: int, source_message_id: int):
    """Pending ⏰-reaction reminder for this user/message, if any."""
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM reminders WHERE user_id=? AND source_message_id=?"
            " AND done=0 ORDER BY due_at ASC LIMIT 1",
            (user_id, source_message_id)).fetchone()


def update_reminder(reminder_id: int, message: str | None = None,
                    due_at: datetime | None = None) -> bool:
    """Update a pending reminder's message and/or due time."""
    if message is None and due_at is None:
        return False
    sets, params = [], []
    if message is not None:
        sets.append("message=?")
        params.append(message)
    if due_at is not None:
        sets.append("due_at=?")
        params.append(due_at.astimezone(timezone.utc).isoformat())
    params.append(reminder_id)
    with _conn() as conn:
        cur = conn.execute(
            f"UPDATE reminders SET {', '.join(sets)} WHERE id=? AND done=0",
            params)
        return cur.rowcount > 0


def update_due(table: str, row_id: int, due_at: datetime) -> None:
    assert table in ("reminders", "scheduled_announcements")
    with _conn() as conn:
        conn.execute(f"UPDATE {table} SET due_at=? WHERE id=?",
                     (due_at.astimezone(timezone.utc).isoformat(), row_id))


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
