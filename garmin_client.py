import logging
from datetime import date, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

BADGES_API = "https://api.garminbadges.com/api/badges"


def _fetch_all() -> list[dict]:
    resp = requests.get(BADGES_API, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _available_in_poland(badge: dict) -> bool:
    countries = badge.get("countries") or []
    return not countries or any(c.get("id") == "PL" for c in countries)


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s[:19])


def fetch_badge_updates() -> dict:
    """Return badges whose end_date falls within the current Mon–Sun week."""
    badges = _fetch_all()

    now = datetime.now()
    week_monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_sunday = week_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    available = []
    for b in badges:
        if b.get("premium"):
            continue
        if not _available_in_poland(b):
            continue
        end_str = b.get("end_date")
        if not end_str:
            continue
        try:
            end_dt = _parse_dt(end_str)
        except Exception:
            continue
        if week_monday <= end_dt <= week_sunday:
            available.append(b)

    available.sort(key=lambda b: b.get("end_date") or "9999")
    logger.info("Available badges this week: %d", len(available))
    return {"available_challenges": available}


def fetch_today_special_badges() -> list[dict]:
    """Return badges where start and end share today's month+day (annual single-day badges)."""
    badges = _fetch_all()
    today = date.today()

    result = []
    for b in badges:
        if b.get("premium"):
            continue
        if not _available_in_poland(b):
            continue
        start_str = b.get("start_date")
        end_str = b.get("end_date")
        if not start_str or not end_str:
            continue
        try:
            start_dt = _parse_dt(start_str).date()
            end_dt = _parse_dt(end_str).date()
        except Exception:
            continue
        same_day = start_dt.month == end_dt.month and start_dt.day == end_dt.day
        is_today = start_dt.month == today.month and start_dt.day == today.day
        if same_day and is_today:
            result.append(b)

    logger.info("Today-special badges: %d", len(result))
    return result
