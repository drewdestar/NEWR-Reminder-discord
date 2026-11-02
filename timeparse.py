"""Time parsing for NEWR Reminder.

All user input is interpreted in Asia/Jakarta (WIB, UTC+7) and the
result is an aware UTC datetime, which is what is stored in SQLite.

Accepted formats:
  Relative: 10m, 2h, 1d, 30s, 1w, and combinations like 1h30m or 1h 30m
  Absolute: YYYY-MM-DD HH:MM            (interpreted as WIB)
            YYYY-MM-DD HH:MM WIB        (same, explicit suffix)
            YYYY-MM-DD HH:MM UTC        (interpreted as UTC, not WIB)
            YYYY-MM-DD HH:MM:SS         (seconds optional)
  Natural language (WIB, own implementation, no copied code):
            today 18:30, tomorrow 20:00, tomorrow 09:00 WIB
            friday 19:00, next friday 19:00, next monday 09:00
            (weekday names in full or 3-letter abbreviation)

  Weekday rule, documented so it is predictable: a bare weekday means
  the next occurrence of that weekday, today included if its time is
  still in the future; "next <weekday>" never means today -- it is the
  first occurrence strictly after today (1-7 days ahead). "today" with
  a time already passed, and any date/time in the past, is an error.

Anything else, or a time in the past, raises ValueError with a
human-readable message. Callers must turn that into a reply, never
let it crash the command.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:  # pragma: no cover - fallback if tzdata is missing
    WIB = timezone(timedelta(hours=7))

UTC = timezone.utc

_RELATIVE_RE = re.compile(r"^\s*(?:(\d+)\s*w)?(?:(\d+)\s*d)?(?:(\d+)\s*h)?"
                          r"(?:(\d+)\s*m)?(?:(\d+)\s*s)?\s*$")
_RELATIVE_TOKEN_RE = re.compile(r"(\d+)\s*([smhdw])")
_ABSOLUTE_RE = re.compile(
    r"^\s*(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?"
    r"\s*(wib|utc|\+07:00|\+00:00)?\s*$", re.IGNORECASE)
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(wib|utc)?$",
                      re.IGNORECASE)

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
_NATURAL_RE = re.compile(
    r"^\s*(?:(next)\s+)?(today|tomorrow|monday|mon|tuesday|tue|tues|"
    r"wednesday|wed|thursday|thu|thur|thurs|friday|fri|saturday|sat|"
    r"sunday|sun)\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(wib|utc)?\s*$",
    re.IGNORECASE)

FORMAT_HELP = (
    "Use a relative time like `10m`, `2h`, `1d`, or `1h30m`, "
    "an absolute time like `2026-11-02 09:00 WIB`, "
    "or a natural time like `tomorrow 20:00`, `today 18:30`, "
    "or `next friday 19:00`."
)


def _check_future(due: datetime, now_utc: datetime, raw: str) -> datetime:
    if due <= now_utc:
        raise ValueError(
            f"`{raw}` is in the past. Please pick a future time. {FORMAT_HELP}")
    return due


def _parse_natural(raw: str, now_utc: datetime) -> datetime | None:
    """Return a UTC datetime for natural input, or None if not natural.

    Raises ValueError for a natural-looking input with a bad time.
    """
    m = _NATURAL_RE.match(raw)
    if not m:
        return None
    is_next, word, hour_s, minute_s, second_s, suffix = m.groups()
    word = word.lower()
    hour, minute = int(hour_s), int(minute_s)
    second = int(second_s) if second_s else 0
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError(
            f"`{raw}` is not a valid time of day. {FORMAT_HELP}")
    tz = UTC if (suffix or "").lower() == "utc" else WIB
    now_local = now_utc.astimezone(tz)
    if word == "today":
        if is_next:
            raise ValueError(
                f"`{raw}` does not make sense; use `tomorrow` instead. {FORMAT_HELP}")
        target_date = now_local.date()
    elif word == "tomorrow":
        target_date = now_local.date() + timedelta(days=1)
    else:
        target_weekday = _WEEKDAYS[word]
        today_weekday = now_local.weekday()
        if is_next:
            # Never today: 1-7 days ahead.
            days_ahead = (target_weekday - today_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7
        else:
            days_ahead = (target_weekday - today_weekday) % 7
            # days_ahead == 0 means today; the future check below
            # rejects it if the time has already passed.
        target_date = now_local.date() + timedelta(days=days_ahead)
    try:
        local = datetime(target_date.year, target_date.month, target_date.day,
                         hour, minute, second, tzinfo=tz)
    except ValueError:
        raise ValueError(
            f"`{raw}` is not a valid date/time. {FORMAT_HELP}") from None
    return _check_future(local.astimezone(UTC), now_utc, raw)


def parse_time(text: str, now: datetime | None = None) -> datetime:
    """Parse *text* into an aware UTC datetime in the future.

    Raises ValueError with a clear message on invalid or past input.
    """
    if text is None or not str(text).strip():
        raise ValueError(f"Time is empty. {FORMAT_HELP}")
    raw = str(text).strip()
    now_utc = now.astimezone(UTC) if now is not None else datetime.now(UTC)

    # --- Relative: one or more <number><unit> tokens, nothing else. ---
    tokens = _RELATIVE_TOKEN_RE.findall(raw.lower())
    if tokens and "".join(f"{n}{u}" for n, u in tokens) == re.sub(
            r"\s+", "", raw.lower()):
        delta = timedelta()
        for amount, unit in tokens:
            value = int(amount)
            if unit == "s":
                delta += timedelta(seconds=value)
            elif unit == "m":
                delta += timedelta(minutes=value)
            elif unit == "h":
                delta += timedelta(hours=value)
            elif unit == "d":
                delta += timedelta(days=value)
            elif unit == "w":
                delta += timedelta(weeks=value)
        if delta.total_seconds() <= 0:
            raise ValueError(f"Time must be in the future. {FORMAT_HELP}")
        return now_utc + delta

    # --- Absolute: YYYY-MM-DD HH:MM, WIB unless UTC is stated. ---
    m = _ABSOLUTE_RE.match(raw)
    if m:
        year, month, day, hour, minute = (int(m.group(i)) for i in range(1, 6))
        second = int(m.group(6)) if m.group(6) else 0
        suffix = (m.group(7) or "wib").lower()
        tz = UTC if suffix in ("utc", "+00:00") else WIB
        try:
            local = datetime(year, month, day, hour, minute, second, tzinfo=tz)
        except ValueError:
            raise ValueError(
                f"`{raw}` is not a valid date/time. {FORMAT_HELP}") from None
        due = local.astimezone(UTC)
        if due <= now_utc:
            raise ValueError(
                f"`{raw}` is in the past. Please pick a future time. {FORMAT_HELP}")
        return due

    # --- Natural language: today/tomorrow/weekday + HH:MM (WIB). ---
    natural = _parse_natural(raw, now_utc)
    if natural is not None:
        return natural

    raise ValueError(f"Could not understand time `{raw}`. {FORMAT_HELP}")


def next_recurrence(due_utc: datetime, repeat: str) -> datetime | None:
    """Next occurrence after *due_utc* for 'daily'/'weekly', else None."""
    if repeat == "daily":
        return due_utc + timedelta(days=1)
    if repeat == "weekly":
        return due_utc + timedelta(weeks=1)
    return None


def format_wib(utc_iso: str) -> str:
    """Render a stored UTC ISO string as 'YYYY-MM-DD HH:%M WIB'."""
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(WIB).strftime("%Y-%m-%d %H:%M WIB")
    except Exception:
        return utc_iso
