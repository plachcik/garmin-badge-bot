"""Tests for message_builder.py — all pure functions, no I/O."""
from datetime import datetime, timedelta

from message_builder import (
    DIFFICULTY_STARS,
    _badge_line,
    _days_left,
    _e,
    _format_date,
    _format_target,
    build_daily_message,
    build_today_special_message,
)

# ---------------------------------------------------------------------------
# _e — MarkdownV2 escaping
# ---------------------------------------------------------------------------

class TestEscape:
    def test_plain_text_unchanged(self):
        assert _e("hello world") == "hello world"

    def test_escapes_exclamation(self):
        assert _e("Żeby nie umknęło!") == "Żeby nie umknęło\\!"

    def test_escapes_dot(self):
        assert _e("3.14") == "3\\.14"

    def test_escapes_dash(self):
        assert _e("a-b") == "a\\-b"

    def test_escapes_parentheses(self):
        assert _e("(łącznie)") == "\\(łącznie\\)"

    def test_escapes_all_special_chars(self):
        special = r"_*[]()~`>#+-=|{}.!"
        result = _e(special)
        for ch in special:
            assert f"\\{ch}" in result

    def test_empty_string(self):
        assert _e("") == ""

    def test_polish_chars_untouched(self):
        # Polish diacritics have no special meaning in MarkdownV2
        assert _e("ąęśćżźółń") == "ąęśćżźółń"


# ---------------------------------------------------------------------------
# _format_target — unit conversion
# ---------------------------------------------------------------------------

class TestFormatTarget:
    def test_distance_meters_to_km(self):
        badge = {"badgeTargetValue": 10000, "badgeUnitId": 1}
        assert _format_target(badge) == "10 km"

    def test_elevation_small(self):
        badge = {"badgeTargetValue": 500, "badgeUnitId": 2}
        assert _format_target(badge) == "500 m"

    def test_elevation_large(self):
        badge = {"badgeTargetValue": 2500, "badgeUnitId": 2}
        assert _format_target(badge) == "2.5 km"

    def test_repetitions(self):
        badge = {"badgeTargetValue": 5, "badgeUnitId": 3}
        assert _format_target(badge) == "5×"

    def test_steps(self):
        badge = {"badgeTargetValue": 10000, "badgeUnitId": 5}
        assert _format_target(badge) == "10,000 steps"

    def test_duration_hours(self):
        badge = {"badgeTargetValue": 7200, "badgeUnitId": 7}
        assert _format_target(badge) == "2 h"

    def test_unknown_unit_returns_raw(self):
        badge = {"badgeTargetValue": 42, "badgeUnitId": 99}
        assert _format_target(badge) == "42"

    def test_no_target_returns_empty(self):
        assert _format_target({}) == ""

    def test_no_unit_returns_raw(self):
        badge = {"badgeTargetValue": 7}
        assert _format_target(badge) == "7"


# ---------------------------------------------------------------------------
# _format_date
# ---------------------------------------------------------------------------

class TestFormatDate:
    def test_iso_date(self):
        assert _format_date("2024-06-15T23:59:59") == "Jun 15"

    def test_iso_date_with_trailing_zeros(self):
        # garmin sometimes has "2024-06-15T23:59:59.000000"
        assert _format_date("2024-06-15T23:59:59.000000") == "Jun 15"

    def test_none_returns_empty(self):
        assert _format_date(None) == ""

    def test_empty_returns_empty(self):
        assert _format_date("") == ""

    def test_unparseable_returns_original(self):
        assert _format_date("not-a-date") == "not-a-date"


# ---------------------------------------------------------------------------
# _days_left
# ---------------------------------------------------------------------------

class TestDaysLeft:
    def _future(self, days: int) -> str:
        return (datetime.now() + timedelta(days=days, hours=1)).isoformat()

    def _past(self, days: int) -> str:
        return (datetime.now() - timedelta(days=days)).isoformat()

    def test_today_returns_last_day(self):
        # end = now + 30 minutes → still "today"
        end = (datetime.now() + timedelta(minutes=30)).isoformat()
        assert _days_left(end) == "ostatni dzień!"

    def test_tomorrow(self):
        assert _days_left(self._future(1)) == "jeszcze 1 dni"

    def test_five_days(self):
        assert _days_left(self._future(5)) == "jeszcze 5 dni"

    def test_past_returns_minelo(self):
        assert _days_left(self._past(1)) == "minęło"

    def test_none_returns_empty(self):
        assert _days_left(None) == ""

    def test_empty_returns_empty(self):
        assert _days_left("") == ""


# ---------------------------------------------------------------------------
# _badge_line
# ---------------------------------------------------------------------------

class TestBadgeLine:
    def _badge(self, **kwargs):
        end = (datetime.now() + timedelta(days=3)).isoformat()
        defaults = {
            "badgeName": "Test Badge",
            "badgeDifficultyId": 1,
            "badgeTargetValue": 5000,
            "badgeUnitId": 1,
            "badgeEndDate": end,
            "badgeAssocType": "none",
        }
        defaults.update(kwargs)
        return defaults

    def test_name_appears_bold(self):
        line = _badge_line(self._badge(badgeName="My Badge"))
        assert "*My Badge*" in line

    def test_difficulty_stars_1(self):
        line = _badge_line(self._badge(badgeDifficultyId=1))
        assert DIFFICULTY_STARS[1] in line

    def test_difficulty_stars_3(self):
        line = _badge_line(self._badge(badgeDifficultyId=3))
        assert DIFFICULTY_STARS[3] in line

    def test_target_rendered(self):
        line = _badge_line(self._badge(badgeTargetValue=5000, badgeUnitId=1))
        assert "5 km" in line

    def test_end_date_rendered(self):
        line = _badge_line(self._badge())
        assert "Kończy się" in line

    def test_days_left_rendered(self):
        line = _badge_line(self._badge())
        assert "jeszcze" in line or "ostatni" in line

    def test_no_target_skips_goal_line(self):
        # Remove both target AND assoc so the 🎯 line is truly empty
        badge = self._badge()
        del badge["badgeTargetValue"]
        badge["badgeAssocType"] = ""
        line = _badge_line(badge)
        assert "🎯" not in line

    def test_no_end_date_skips_deadline(self):
        badge = self._badge(badgeEndDate=None)
        line = _badge_line(badge)
        assert "Kończy się" not in line


# ---------------------------------------------------------------------------
# build_daily_message
# ---------------------------------------------------------------------------

class TestBuildDailyMessage:
    def _available_badge(self, name="Badge A", days_until_end=3):
        end = (datetime.now() + timedelta(days=days_until_end)).isoformat()
        return {
            "badgeName": name,
            "badgeDifficultyId": 2,
            "badgeTargetValue": 10000,
            "badgeUnitId": 5,
            "badgeEndDate": end,
            "badgeAssocType": "none",
        }

    def _earned_badge(self, name="Earned Badge"):
        return {"badgeName": name, "badgeId": "123"}

    def test_empty_data_returns_no_badges_message(self):
        msg = build_daily_message({"newly_earned": [], "available_challenges": []})
        assert "Brak nowych odznak" in msg
        assert "Ruszaj się" in msg

    def test_header_always_present(self):
        msg = build_daily_message({"newly_earned": [], "available_challenges": []})
        assert "Żeby nie umknęło" in msg

    def test_available_section_heading(self):
        msg = build_daily_message({
            "newly_earned": [],
            "available_challenges": [self._available_badge()],
        })
        assert "Dostępne odznaki w tym tygodniu" in msg

    def test_available_badge_name_in_message(self):
        msg = build_daily_message({
            "newly_earned": [],
            "available_challenges": [self._available_badge("Super Badge")],
        })
        assert "Super Badge" in msg

    def test_newly_earned_section(self):
        msg = build_daily_message({
            "newly_earned": [self._earned_badge("Gold Medal")],
            "available_challenges": [],
        })
        assert "Zdobyte odznaki" in msg
        assert "Gold Medal" in msg
        assert "✅" in msg

    def test_available_sorted_by_end_date(self):
        soon = self._available_badge("Ends Soon", days_until_end=1)
        later = self._available_badge("Ends Later", days_until_end=5)
        msg = build_daily_message({
            "newly_earned": [],
            "available_challenges": [later, soon],  # intentionally wrong order
        })
        assert msg.index("Ends Soon") < msg.index("Ends Later")

    def test_multiple_available_badges(self):
        badges = [self._available_badge(f"Badge {i}") for i in range(3)]
        msg = build_daily_message({"newly_earned": [], "available_challenges": badges})
        for i in range(3):
            assert f"Badge {i}" in msg

    def test_missing_keys_handled_gracefully(self):
        # Completely empty badge dict — should not raise
        build_daily_message({"newly_earned": [{}], "available_challenges": [{}]})

    def test_message_is_string(self):
        msg = build_daily_message({"newly_earned": [], "available_challenges": []})
        assert isinstance(msg, str)


# ---------------------------------------------------------------------------
# build_today_special_message
# ---------------------------------------------------------------------------

class TestBuildTodaySpecialMessage:
    def _badge(self, name="Special Badge"):
        end = (datetime.now() + timedelta(hours=12)).isoformat()
        return {
            "badgeName": name,
            "badgeDifficultyId": 1,
            "badgeTargetValue": 5000,
            "badgeUnitId": 1,
            "badgeEndDate": end,
            "badgeAssocType": "none",
        }

    def test_header_zeby_nie_umknelo(self):
        msg = build_today_special_message([self._badge()])
        assert "Żeby nie umknęło" in msg

    def test_header_lightbulb_emoji(self):
        msg = build_today_special_message([self._badge()])
        assert "💡" in msg

    def test_section_heading(self):
        msg = build_today_special_message([self._badge()])
        assert "Dostępne odznaki tylko na dziś" in msg

    def test_calendar_emoji_in_section(self):
        msg = build_today_special_message([self._badge()])
        assert "📅" in msg

    def test_tylko_dzis_instead_of_date(self):
        msg = build_today_special_message([self._badge()])
        assert "Tylko dziś" in msg
        assert "Kończy się" not in msg

    def test_badge_name_in_message(self):
        msg = build_today_special_message([self._badge("Rare Badge")])
        assert "Rare Badge" in msg

    def test_multiple_badges_all_present(self):
        badges = [self._badge(f"Badge {i}") for i in range(3)]
        msg = build_today_special_message(badges)
        for i in range(3):
            assert f"Badge {i}" in msg

    def test_returns_string(self):
        assert isinstance(build_today_special_message([self._badge()]), str)
