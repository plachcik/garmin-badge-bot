from datetime import date, datetime

DIFFICULTY_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐"}

IMAGE_BASE_URL = "https://api.garminbadges.com/storage/badges/"


def badge_image_url(badge: dict) -> str | None:
    image_path = badge.get("image_path")
    return f"{IMAGE_BASE_URL}{image_path}" if image_path else None

_MONTHS_PL = [
    "", "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
]


def _format_date_pl(date_str: str | None) -> str:
    """Return a Polish date string like '12 czerwca'."""
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str[:19])
        return f"{dt.day} {_MONTHS_PL[dt.month]}"
    except Exception:
        return date_str or ""


def _format_goal(badge: dict) -> str:
    """Return a formatted goal string like '100,000 steps (łącznie)' or '' if no target."""
    target_str = badge.get("target_value")
    if not target_str:
        return ""
    target = float(target_str)
    desc = (badge.get("description") or "").lower()

    if "step" in desc:
        formatted = f"{int(target):,} steps"
    elif "calorie" in desc or "kcal" in desc:
        formatted = f"{int(target):,} kcal"
    elif ("hour" in desc or "time" in desc) and target >= 3600:
        hours = target / 3600
        formatted = f"{hours:.0f} h" if hours == int(hours) else f"{hours:.1f} h"
    elif "kilometer" in desc:
        formatted = f"{int(target / 1000)} km" if target >= 1000 else f"{int(target)} km"
    elif "meter" in desc:
        formatted = f"{target / 1000:.0f} km" if target >= 1000 else f"{int(target)} m"
    else:
        formatted = (
            str(int(target)) if target == int(target) else target_str.rstrip("0").rstrip(".")
        )

    assoc = (
        "jedna aktywność" if " activity" in desc and "activities" not in desc else "łącznie"
    )

    return f"{formatted} ({assoc})"


def _badge_line(badge: dict) -> str:
    name = badge.get("name", "Unknown")
    difficulty = DIFFICULTY_STARS.get(badge.get("difficulty_id", 1), "")
    goal = _format_goal(badge)
    start_fmt = _format_date_pl(badge.get("start_date"))
    end_fmt = _format_date_pl(badge.get("end_date"))

    line = f"• *{_e(name)}* {difficulty}\n"
    if goal:
        line += f"  🎯 {_e(goal)}\n"
    if start_fmt and end_fmt:
        try:
            start_dt = datetime.fromisoformat(badge["start_date"][:19]).date()
            end_dt = datetime.fromisoformat(badge["end_date"][:19]).date()
            same_day = start_dt.month == end_dt.month and start_dt.day == end_dt.day
        except Exception:
            same_day = False
            start_dt = None
        if same_day:
            line += f"  ⏰ {_e(f'Wyzwanie tylko {end_fmt}!')}\n"
        else:
            started = start_dt is not None and start_dt < date.today()
            verb = "Wyzwanie zaczęło się" if started else "Wyzwanie zaczyna się"
            line += f"  ⏰ {_e(f'{verb} {start_fmt} a kończy {end_fmt}')}\n"
    elif end_fmt:
        line += f"  ⏰ {_e(f'Kończy się {end_fmt}')}\n"
    return line


def _badge_line_today(badge: dict) -> str:
    """Badge line variant for today-only badges — replaces deadline with 'Tylko dziś!!'."""
    name = badge.get("name", "Unknown")
    difficulty = DIFFICULTY_STARS.get(badge.get("difficulty_id", 1), "")
    goal = _format_goal(badge)

    line = f"• *{_e(name)}* {difficulty}\n"
    if goal:
        line += f"  🎯 {_e(goal)}\n"
    line += "  ⏰ Tylko dziś\\!\\! Rusz dupę\\!\\!\n"
    return line


def badge_caption(badge: dict, today_only: bool = False) -> str:
    """Return a MarkdownV2 caption for a photo message (no bullet point, no indent)."""
    name = badge.get("name", "Unknown")
    difficulty = DIFFICULTY_STARS.get(badge.get("difficulty_id", 1), "")
    goal = _format_goal(badge)

    text = f"*{_e(name)}* {difficulty}\n"
    if goal:
        text += f"🎯 {_e(goal)}\n"

    if today_only:
        text += "⏰ Tylko dziś\\!\\! Rusz dupę\\!\\!\n"
    else:
        start_fmt = _format_date_pl(badge.get("start_date"))
        end_fmt = _format_date_pl(badge.get("end_date"))
        if start_fmt and end_fmt:
            try:
                start_dt = datetime.fromisoformat(badge["start_date"][:19]).date()
                end_dt = datetime.fromisoformat(badge["end_date"][:19]).date()
                same_day = start_dt.month == end_dt.month and start_dt.day == end_dt.day
            except Exception:
                same_day = False
                start_dt = None
            if same_day:
                text += f"⏰ {_e(f'Wyzwanie tylko {end_fmt}!')}\n"
            else:
                started = start_dt is not None and start_dt < date.today()
                verb = "Wyzwanie zaczęło się" if started else "Wyzwanie zaczyna się"
                text += f"⏰ {_e(f'{verb} {start_fmt} a kończy {end_fmt}')}\n"
        elif end_fmt:
            text += f"⏰ {_e(f'Kończy się {end_fmt}')}\n"

    return text.rstrip("\n")


def build_today_special_message(badges: list[dict]) -> str:
    """Message for same-day annual badges available only today."""
    lines = [
        "Żeby nie umknęło 💡\n",
        "*📅 Dostępne odznaki tylko na dziś:*\n",
    ]
    for b in badges:
        lines.append(_badge_line_today(b))
    return "\n".join(lines)


def build_daily_message(data: dict, header: str | None = None) -> str:
    available = data.get("available_challenges", [])
    header_line = header if header is not None else "👋🏻 *Żeby nie umknęło\\!*"

    if not available:
        return (
            f"{header_line}\n\n"
            "Brak aktywnych wyzwań w tym tygodniu\\. Ruszaj się\\! 🚶"
        )

    lines = [f"{header_line}\n"]
    if header is None:
        lines.append("*Dostępne odznaki w tym tygodniu:*\n")
    for b in available:
        lines.append(_badge_line(b))

    return "\n".join(lines)


def weekly_digest_header(header: str | None = None) -> str:
    """Header text sent before the badge photo stream."""
    if header is not None:
        return header
    return "👋🏻 *Żeby nie umknęło\\!*\n\n*Dostępne odznaki w tym tygodniu:*"


def today_special_header() -> str:
    return "Żeby nie umknęło 💡\n\n*📅 Dostępne odznaki tylko na dziś:*"


def _e(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text
