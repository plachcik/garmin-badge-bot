"""Tests for message_builder.py — all pure functions, no I/O."""
from datetime import datetime, timedelta

from message_builder import (
    DIFFICULTY_STARS,
    _badge_line,
    _e,
    _format_date_pl,
    _format_goal,
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
        assert _e("ąęśćżźółń") == "ąęśćżźółń"


# ---------------------------------------------------------------------------
# _format_date_pl
# ---------------------------------------------------------------------------

class TestFormatDatePl:
    def test_june(self):
        assert _format_date_pl("2024-06-15T23:59:59") == "15 czerwca"

    def test_january(self):
        assert _format_date_pl("2024-01-01T00:00:00") == "1 stycznia"

    def test_december(self):
        assert _format_date_pl("2024-12-31T23:59:59") == "31 grudnia"

    def test_with_microseconds(self):
        assert _format_date_pl("2026-06-12T00:00:00.000000Z") == "12 czerwca"

    def test_none_returns_empty(self):
        assert _format_date_pl(None) == ""

    def test_empty_returns_empty(self):
        assert _format_date_pl("") == ""

    def test_unparseable_returns_original(self):
        assert _format_date_pl("not-a-date") == "not-a-date"


# ---------------------------------------------------------------------------
# _badge_line
# ---------------------------------------------------------------------------

class TestBadgeLine:
    def _badge(self, **kwargs):
        defaults = {
            "name": "Test Badge",
            "difficulty_id": 1,
            "description": "Record a 5 km run.",
            "start_date": "2026-06-12T00:00:00.000000Z",
            "end_date": "2026-06-14T23:59:59.000000Z",
        }
        defaults.update(kwargs)
        return defaults

    def test_name_appears_bold(self):
        line = _badge_line(self._badge(name="My Badge"))
        assert "*My Badge*" in line

    def test_difficulty_stars_1(self):
        line = _badge_line(self._badge(difficulty_id=1))
        assert DIFFICULTY_STARS[1] in line

    def test_difficulty_stars_3(self):
        line = _badge_line(self._badge(difficulty_id=3))
        assert DIFFICULTY_STARS[3] in line

    def test_goal_rendered(self):
        badge = self._badge()
        badge["target_value"] = "1000.00"
        badge["description"] = "Record 1,000 meters of swimming activities."
        line = _badge_line(badge)
        assert "🎯" in line
        assert "km" in line

    def test_start_and_end_date_rendered(self):
        line = _badge_line(self._badge())
        assert "Wyzwanie zaczyna się 12 czerwca a kończy 14 czerwca" in line

    def test_same_day_shows_tylko(self):
        badge = self._badge(
            start_date="2026-06-13T00:00:00.000000Z",
            end_date="2026-06-13T23:59:59.000000Z",
        )
        line = _badge_line(badge)
        assert "Wyzwanie tylko 13 czerwca" in line
        assert "zaczyna się" not in line
        assert "kończy" not in line

    def test_only_end_date_rendered_when_no_start(self):
        badge = self._badge(start_date=None)
        line = _badge_line(badge)
        assert "Kończy się 14 czerwca" in line
        assert "Wyzwanie zaczyna się" not in line

    def test_polish_month_name(self):
        badge = self._badge(
            start_date="2026-01-01T00:00:00",
            end_date="2026-01-03T23:59:59",
        )
        line = _badge_line(badge)
        assert "stycznia" in line

    def test_no_target_skips_goal_line(self):
        badge = self._badge()
        badge["target_value"] = None
        line = _badge_line(badge)
        assert "🎯" not in line

    def test_no_dates_skips_deadline(self):
        badge = self._badge(start_date=None, end_date=None)
        line = _badge_line(badge)
        assert "⏰" not in line

    def test_past_start_uses_zaczelo_sie(self):
        badge = self._badge(start_date="2026-01-01T00:00:00")
        line = _badge_line(badge)
        assert "Wyzwanie zaczęło się" in line


# ---------------------------------------------------------------------------
# _format_goal
# ---------------------------------------------------------------------------

class TestFormatGoal:
    def test_steps(self):
        b = {"target_value": "100000.00", "description": "Record 100,000 steps in June."}
        assert _format_goal(b) == "100,000 kroków (łącznie)"

    def test_meters_to_km(self):
        b = {"target_value": "1000.00", "description": "Record 1,000 meters of swimming activities."}  # noqa: E501
        assert _format_goal(b) == "1 km (łącznie)"

    def test_kilometers(self):
        b = {
            "target_value": "100000.00",
            "description": "Record 100 kilometers of cycling activities.",
        }
        assert _format_goal(b) == "100 km (łącznie)"

    def test_hours_from_seconds(self):
        b = {
            "target_value": "10800.00",
            "description": "Record at least 3 hours of cardio activities.",
        }
        assert _format_goal(b) == "3 h (łącznie)"

    def test_calories(self):
        b = {"target_value": "8000.00", "description": "Burn 8,000 active calories in June."}
        assert _format_goal(b) == "8,000 kcal (łącznie)"

    def test_single_activity(self):
        b = {"target_value": "10000.00", "description": "Record a 10-kilometer running activity."}
        assert "(jedna aktywność)" in _format_goal(b)

    def test_no_target_returns_empty(self):
        assert _format_goal({"target_value": None}) == ""

    def test_missing_target_returns_empty(self):
        assert _format_goal({}) == ""


# ---------------------------------------------------------------------------
# build_daily_message
# ---------------------------------------------------------------------------

class TestBuildDailyMessage:
    def _available_badge(self, name="Badge A", days_until_end=3):
        start = datetime.now().isoformat()
        end = (datetime.now() + timedelta(days=days_until_end)).isoformat()
        return {
            "name": name,
            "difficulty_id": 2,
            "description": "Join this challenge.",
            "start_date": start,
            "end_date": end,
        }

    def test_empty_data_returns_no_badges_message(self):
        msg = build_daily_message({"available_challenges": []})
        assert "Brak aktywnych wyzwań" in msg
        assert "Ruszaj się" in msg

    def test_header_always_present(self):
        msg = build_daily_message({"available_challenges": []})
        assert "👋🏻" in msg
        assert "Żeby nie umknęło" in msg

    def test_available_section_heading(self):
        msg = build_daily_message({"available_challenges": [self._available_badge()]})
        assert "Dostępne odznaki w tym tygodniu" in msg

    def test_available_badge_name_in_message(self):
        msg = build_daily_message({"available_challenges": [self._available_badge("Super Badge")]})
        assert "Super Badge" in msg

    def test_multiple_available_badges(self):
        badges = [self._available_badge(f"Badge {i}") for i in range(3)]
        msg = build_daily_message({"available_challenges": badges})
        for i in range(3):
            assert f"Badge {i}" in msg

    def test_custom_header_used(self):
        msg = build_daily_message(
            {"available_challenges": []},
            header="👋🏻 *Dostępne odznaki w tym tygodniu:*",
        )
        assert "Dostępne odznaki w tym tygodniu" in msg
        assert "Żeby nie umknęło" not in msg

    def test_missing_keys_handled_gracefully(self):
        build_daily_message({"available_challenges": [{}]})

    def test_message_is_string(self):
        assert isinstance(build_daily_message({"available_challenges": []}), str)


# ---------------------------------------------------------------------------
# build_today_special_message
# ---------------------------------------------------------------------------

class TestBuildTodaySpecialMessage:
    def _badge(self, name="Special Badge"):
        end = (datetime.now() + timedelta(hours=12)).isoformat()
        return {
            "name": name,
            "difficulty_id": 1,
            "description": "Record an activity today.",
            "end_date": end,
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


# ---------------------------------------------------------------------------
# _badge_line — single-day badges
# ---------------------------------------------------------------------------

class TestBadgeLineSingleDay:
    def _single_day_badge(self, month=7, day=4, **kwargs):
        defaults = {
            "name": "Single Day Badge",
            "difficulty_id": 1,
            "description": "Record an activity on this day.",
            "start_date": f"2019-{month:02d}-{day:02d}T00:00:00",
            "end_date": f"2026-{month:02d}-{day:02d}T23:59:59",
        }
        defaults.update(kwargs)
        return defaults

    def test_same_day_start_and_end_month_match(self):
        badge = self._single_day_badge(month=7, day=4)
        start = datetime.fromisoformat(badge["start_date"])
        end = datetime.fromisoformat(badge["end_date"])
        assert start.month == end.month
        assert start.day == end.day

    def test_single_day_badge_line_rendered(self):
        badge = self._single_day_badge(month=7, day=4)
        line = _badge_line(badge)
        assert "Single Day Badge" in line
        assert "⏰" in line

    def test_single_day_shows_tylko_format(self):
        badge = self._single_day_badge(month=7, day=4)
        line = _badge_line(badge)
        assert "Wyzwanie tylko 4 lipca" in line
        assert line.count("lipca") == 1

    def test_single_day_june(self):
        badge = self._single_day_badge(month=6, day=11)
        line = _badge_line(badge)
        assert "11 czerwca" in line

    def test_today_special_message_uses_tylko_dzis(self):
        badge = self._single_day_badge()
        msg = build_today_special_message([badge])
        assert "Tylko dziś" in msg
        assert "Zaczyna się" not in msg

    def test_today_special_hides_dates(self):
        badge = self._single_day_badge(month=12, day=25)
        msg = build_today_special_message([badge])
        assert "grudnia" not in msg
        assert "Tylko dziś" in msg
