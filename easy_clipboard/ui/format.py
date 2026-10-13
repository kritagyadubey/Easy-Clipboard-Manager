"""Human-friendly time and size formatting."""

from __future__ import annotations

import time


def relative_time(timestamp: float, now: float | None = None) -> str:
    """Return "Just now", "5 minutes ago", "yesterday", or a date."""
    if now is None:
        now = time.time()
    delta = max(0.0, now - timestamp)

    if delta < 45:
        return "Just now"
    if delta < 90:
        return "1 minute ago"
    minutes = int(delta // 60)
    if minutes < 60:
        return f"{minutes} minutes ago"
    hours = int(delta // 3600)
    if hours == 1:
        return "1 hour ago"
    if hours < 24:
        return f"{hours} hours ago"
    days = int(delta // 86400)
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        weeks = int(days // 7)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    local = time.localtime(timestamp)
    if local.tm_year == time.localtime(now).tm_year:
        return time.strftime("%b %d", local)
    return time.strftime("%b %d, %Y", local)


def full_time(timestamp: float) -> str:
    """Full local date and time, e.g. "Oct 13, 2026 at 14:05:22"."""
    return time.strftime("%b %d, %Y at %H:%M:%S", time.localtime(timestamp))


def short_date(timestamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))


def count_label(count: int, singular: str = "entry", plural: str = "entries") -> str:
    return f"{count:,} {singular if count == 1 else plural}"


def char_label(count: int) -> str:
    if count < 1000:
        return f"{count} chars"
    return f"{count / 1000:.1f}k chars"
