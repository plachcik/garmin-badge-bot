from datetime import datetime

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


def _format_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%b %d")
    except Exception:
        return date_str


def _days_left(end_str: str | None) -> str:
    if not end_str:
        return ""
    try:
        end = datetime.fromisoformat(end_str)
        delta = (end - datetime.now()).days
        if delta < 0:
            return "minęło"
        if delta == 0:
            return "ostatni dzień!"
        return f"jeszcze {delta} dni"
    except Exception:
        return ""


def _badge_line(badge: dict) -> str:
    name = badge.get("badgeName", "Unknown")
    difficulty = DIFFICULTY_STARS.get(badge.get("badgeDifficultyId", 1), "")
    target = _format_target(badge)
    assoc = ASSOC_TYPE_LABEL.get(badge.get("badgeAssocType", ""), "")
    end = badge.get("badgeEndDate")
    days = _days_left(end)
    end_fmt = _format_date(end)

    # Build "what to do" line
    what = []
    if target:
        what.append(target)
    if assoc:
        what.append(f"({assoc})")

    line = f"• *{_e(name)}* {difficulty}\n"
    if what:
        line += f"  🎯 {_e(' '.join(what))}\n"
    if end_fmt:
        line += f"  ⏰ Kończy się {_e(end_fmt)}"
        if days:
            line += f" — {_e(days)}"
        line += "\n"
    return line


def build_daily_message(data: dict) -> str:
    newly_earned = data.get("newly_earned", [])
    available = data.get("available_challenges", [])

    if not newly_earned and not available:
        return (
            "👋 *Żeby nie umknęło\\!*\n\n"
            "Brak nowych odznak i aktywnych wyzwań w tym tygodniu\\. Ruszaj się\\! 🚶"
        )

    lines = ["👋 *Żeby nie umknęło\\!*\n"]

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
        lines.append("*Dostępne odznaki w tym tygodniu:*\n")
        for b in available_sorted:
            lines.append(_badge_line(b))

    return "\n".join(lines)


def _e(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text
