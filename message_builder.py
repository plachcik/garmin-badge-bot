from datetime import date, datetime

# badgeUnitId → (label, conversion_fn)
UNIT_MAP = {
    1: ("m",  lambda v: f"{v/1000:.0f} km"),
    2: ("m",  lambda v: f"{v:.0f} m" if v < 1000 else f"{v/1000:.1f} km"),
    3: ("x",  lambda v: f"{v:.0f}×"),
    5: ("steps", lambda v: f"{v:,.0f} steps"),
    7: ("sec", lambda v: f"{v/3600:.0f} h"),
    11: ("likes", lambda v: f"{v:.0f} likes"),
}

DIFFICULTY_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐"}

ASSOC_TYPE_LABEL = {
    "activityId": "jedna aktywność",
    "none": "łącznie",
}


def _format_target(badge: dict) -> str:
    target = badge.get("badgeTargetValue")
    unit_id = badge.get("badgeUnitId")
    if target is None:
        return ""
    if unit_id in UNIT_MAP:
        _, fmt = UNIT_MAP[unit_id]
        return fmt(target)
    return str(target)


_MONTHS_PL = [
    "", "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
]


def _format_date_pl(date_str: str | None) -> str:
    """Return a Polish date string like '12 czerwca'."""
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str)
        return f"{dt.day} {_MONTHS_PL[dt.month]}"
    except Exception:
        return date_str or ""


def _badge_line(badge: dict) -> str:
    name = badge.get("badgeName", "Unknown")
    difficulty = DIFFICULTY_STARS.get(badge.get("badgeDifficultyId", 1), "")
    target = _format_target(badge)
    assoc = ASSOC_TYPE_LABEL.get(badge.get("badgeAssocType", ""), "")
    start_fmt = _format_date_pl(badge.get("badgeStartDate"))
    end_fmt = _format_date_pl(badge.get("badgeEndDate"))

    # Build "what to do" line
    what = []
    if target:
        what.append(target)
    if assoc:
        what.append(f"({assoc})")

    line = f"• *{_e(name)}* {difficulty}\n"
    if what:
        line += f"  🎯 {_e(' '.join(what))}\n"
    if start_fmt and end_fmt:
        try:
            start_dt = datetime.fromisoformat(badge["badgeStartDate"]).date()
            started = start_dt < date.today()
        except Exception:
            started = False
        verb = "Wyzwanie zaczęło się" if started else "Wyzwanie zaczyna się"
        line += f"  ⏰ {_e(f'{verb} {start_fmt} a kończy {end_fmt}')}\n"
    elif end_fmt:
        line += f"  ⏰ {_e(f'Kończy się {end_fmt}')}\n"
    return line


def _badge_line_today(badge: dict) -> str:
    """Badge line variant for today-only badges — replaces deadline with 'Tylko dziś!!'."""
    name = badge.get("badgeName", "Unknown")
    difficulty = DIFFICULTY_STARS.get(badge.get("badgeDifficultyId", 1), "")
    target = _format_target(badge)
    assoc = ASSOC_TYPE_LABEL.get(badge.get("badgeAssocType", ""), "")

    what = []
    if target:
        what.append(target)
    if assoc:
        what.append(f"({assoc})")

    line = f"• *{_e(name)}* {difficulty}\n"
    if what:
        line += f"  🎯 {_e(' '.join(what))}\n"
    line += "  ⏰ Tylko dziś\\!\\!\n"
    return line


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
    newly_earned = data.get("newly_earned", [])
    available = data.get("available_challenges", [])
    header_line = header if header is not None else "👋🏻 *Żeby nie umknęło\\!*"

    if not newly_earned and not available:
        return (
            f"{header_line}\n\n"
            "Brak nowych odznak i aktywnych wyzwań w tym tygodniu\\. Ruszaj się\\! 🚶"
        )

    lines = [f"{header_line}\n"]

    if newly_earned:
        lines.append("🎉 *Zdobyte odznaki:*")
        for b in newly_earned:
            lines.append(f"  ✅ {_e(b.get('badgeName', 'Unknown'))}")
        lines.append("")

    if available:
        available_sorted = sorted(
            available,
            key=lambda b: b.get("badgeEndDate") or "9999"
        )
        # Only add section heading when it's not already in the header
        if header is None:
            lines.append("*Dostępne odznaki w tym tygodniu:*\n")
        for b in available_sorted:
            lines.append(_badge_line(b))

    return "\n".join(lines)


def _e(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text
