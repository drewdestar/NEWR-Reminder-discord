"""Time parsing for NEWR Reminder.

All user input is interpreted in Asia/Jakarta (WIB, UTC+7) and the
result is an aware UTC datetime, which is what is stored in SQLite.

Accepted formats:
  Relative: 10m, 2h, 1d, 30s, 1w, and combinations like 1h30m or 1h 30m
  Absolute: YYYY-MM-DD HH:MM            (interpreted as WIB)
            YYYY-MM-DD HH:MM WIB        (same, explicit suffix)
            YYYY-MM-DD HH:MM UTC        (interpreted as UTC, not WIB)
            YYYY-MM-DD HH:MM:SS         (seconds optional)

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

FORMAT_HELP = (
    "Use a relative time like `10m`, `2h`, `1d`, or `1h30m`, "
    "or an absolute time like `2026-11-02 09:00 WIB`."
)


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

    raise ValueError(f"Could not understand time `{raw}`. {FORMAT_HELP}")


def format_wib(utc_iso: str) -> str:
    """Render a stored UTC ISO string as 'YYYY-MM-DD HH:MM WIB'."""
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(WIB).strftime("%Y-%m-%d %H:%M WIB")
    except Exception:
        return utc_iso
