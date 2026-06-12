"""Tests for garmin_client.py — badge filtering logic against the public API."""
from datetime import datetime, timedelta
from unittest.mock import patch

import garmin_client


def _badge(
    name: str = "Test",
    end_offset_days: int | None = 2,
    start_offset_days: int | None = None,
    badge_id: int = 1,
) -> dict:
    """Build a minimal badge dict matching the garminbadges.com API shape."""
    now = datetime.now()
    week_monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    b: dict = {"id": badge_id, "name": name, "difficulty_id": 1, "description": "Test desc"}
    if end_offset_days is not None:
        b["end_date"] = (week_monday + timedelta(days=end_offset_days)).isoformat()
    else:
        b["end_date"] = None
    if start_offset_days is not None:
        b["start_date"] = (week_monday + timedelta(days=start_offset_days)).isoformat()
    else:
        b["start_date"] = (now - timedelta(days=1)).isoformat()
    return b


# ---------------------------------------------------------------------------
# fetch_badge_updates
# ---------------------------------------------------------------------------

class TestFetchBadgeUpdates:
    def _run(self, badges):
        with patch.object(garmin_client, "_fetch_all", return_value=badges):
            return garmin_client.fetch_badge_updates()

    def test_badge_ending_this_week_included(self):
        result = self._run([_badge("Good", end_offset_days=2)])
        assert any(b["name"] == "Good" for b in result["available_challenges"])

    def test_badge_with_null_end_date_excluded(self):
        result = self._run([_badge("No End", end_offset_days=None)])
        assert result["available_challenges"] == []

    def test_badge_ending_after_this_week_excluded(self):
        far = (datetime.now() + timedelta(days=10)).isoformat()
        result = self._run([{"id": 1, "name": "Future", "end_date": far, "start_date": far}])
        assert result["available_challenges"] == []

    def test_badge_ending_before_this_week_excluded(self):
        past = (datetime.now() - timedelta(days=8)).isoformat()
        result = self._run([{"id": 1, "name": "Past", "end_date": past, "start_date": past}])
        assert result["available_challenges"] == []

    def test_multiple_badges_filtered_correctly(self):
        badges = [
            _badge("Good", end_offset_days=1, badge_id=1),
            _badge("No End", end_offset_days=None, badge_id=2),
        ]
        result = self._run(badges)
        assert len(result["available_challenges"]) == 1
        assert result["available_challenges"][0]["name"] == "Good"

    def test_sorted_by_end_date(self):
        soon = _badge("Soon", end_offset_days=1, badge_id=1)
        later = _badge("Later", end_offset_days=3, badge_id=2)
        result = self._run([later, soon])
        names = [b["name"] for b in result["available_challenges"]]
        assert names.index("Soon") < names.index("Later")

    def test_empty_response_returns_empty_list(self):
        result = self._run([])
        assert result == {"available_challenges": []}

    def test_premium_badge_excluded(self):
        badge = _badge("Premium", end_offset_days=2)
        badge["premium"] = True
        result = self._run([badge])
        assert result["available_challenges"] == []

    def test_non_premium_badge_included(self):
        badge = _badge("Free", end_offset_days=2)
        badge["premium"] = False
        result = self._run([badge])
        assert len(result["available_challenges"]) == 1

    def test_api_failure_propagates(self):
        import pytest
        with (
            patch.object(garmin_client, "_fetch_all", side_effect=RuntimeError("network")),
            pytest.raises(RuntimeError),
        ):
            garmin_client.fetch_badge_updates()


# ---------------------------------------------------------------------------
# fetch_today_special_badges
# ---------------------------------------------------------------------------

class TestFetchTodaySpecialBadges:
    def _make(self, start_year, end_year, month, day, badge_id=1):
        return {
            "id": badge_id,
            "name": f"Badge {badge_id}",
            "difficulty_id": 1,
            "description": "desc",
            "start_date": f"{start_year}-{month:02d}-{day:02d}T00:00:00",
            "end_date": f"{end_year}-{month:02d}-{day:02d}T23:59:59",
        }

    def _run(self, badges):
        with patch.object(garmin_client, "_fetch_all", return_value=badges):
            return garmin_client.fetch_today_special_badges()

    def test_matching_badge_returned(self):
        from datetime import date
        t = date.today()
        badge = self._make(2019, 2030, t.month, t.day)
        result = self._run([badge])
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_different_day_excluded(self):
        from datetime import date, timedelta
        t = date.today() + timedelta(days=1)
        badge = self._make(2019, 2030, t.month, t.day)
        result = self._run([badge])
        assert result == []

    def test_mismatched_start_end_day_excluded(self):
        badge = {
            "id": 1, "name": "Mismatch", "difficulty_id": 1, "description": "d",
            "start_date": "2019-01-01T00:00:00",
            "end_date": "2019-01-02T23:59:59",
        }
        result = self._run([badge])
        assert result == []

    def test_missing_start_date_excluded(self):
        from datetime import date
        t = date.today()
        badge = {
            "id": 1, "name": "No Start", "difficulty_id": 1, "description": "d",
            "start_date": None,
            "end_date": f"{t.year}-{t.month:02d}-{t.day:02d}T23:59:59",
        }
        result = self._run([badge])
        assert result == []

    def test_missing_end_date_excluded(self):
        from datetime import date
        t = date.today()
        badge = {
            "id": 1, "name": "No End", "difficulty_id": 1, "description": "d",
            "start_date": f"2019-{t.month:02d}-{t.day:02d}T00:00:00",
            "end_date": None,
        }
        result = self._run([badge])
        assert result == []

    def test_empty_response_returns_empty_list(self):
        assert self._run([]) == []
