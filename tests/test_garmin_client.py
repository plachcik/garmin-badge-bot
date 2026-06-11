"""Tests for garmin_client.py — state I/O and badge filtering logic."""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import garmin_client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _badge(
    name: str = "Test",
    end_offset_days: int | None = 2,
    earned: bool = False,
    badge_id: str = "1",
) -> dict:
    """Build a minimal badge dict as returned by the Garmin API."""
    now = datetime.now()
    week_monday = now - timedelta(days=now.weekday())
    week_monday = week_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    badge: dict = {
        "badgeName": name,
        "badgeChallengeId": badge_id,
        "badgeId": badge_id,
        "earnedByMe": earned,
    }
    if end_offset_days is not None:
        # End date within current week
        end_dt = week_monday + timedelta(days=end_offset_days)
        badge["badgeEndDate"] = _iso(end_dt)
    else:
        badge["badgeEndDate"] = None
    return badge


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

class TestStateIO:
    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(garmin_client, "STATE_FILE", str(tmp_path / "state.json"))
        state = garmin_client.load_state()
        assert state == {"earned_badge_ids": [], "notified_challenge_ids": []}

    def test_save_and_reload(self, tmp_path, monkeypatch):
        path = str(tmp_path / "state.json")
        monkeypatch.setattr(garmin_client, "STATE_FILE", path)
        data = {"earned_badge_ids": ["1", "2"], "notified_challenge_ids": ["3"]}
        garmin_client.save_state(data)
        assert garmin_client.load_state() == data

    def test_save_writes_valid_json(self, tmp_path, monkeypatch):
        path = str(tmp_path / "state.json")
        monkeypatch.setattr(garmin_client, "STATE_FILE", path)
        garmin_client.save_state({"earned_badge_ids": ["99"], "notified_challenge_ids": []})
        with open(path) as f:
            parsed = json.load(f)
        assert parsed["earned_badge_ids"] == ["99"]


# ---------------------------------------------------------------------------
# fetch_badge_updates — badge filtering logic
# ---------------------------------------------------------------------------

class TestFetchBadgeUpdates:
    """
    These tests patch _get() so no real HTTP calls are made.
    They verify the week-filtering and earned-filtering logic in fetch_badge_updates().
    """

    def _run(self, available_badges, earned_badges=None, tmp_path=None, monkeypatch=None):
        if earned_badges is None:
            earned_badges = []

        # Redirect state file to a temp location so tests don't clash
        monkeypatch.setattr(garmin_client, "STATE_FILE", str(tmp_path / "state.json"))
        # Reset module-level session so get_session() isn't called
        monkeypatch.setattr(garmin_client, "_session", MagicMock())

        def fake_get(path):
            if "earned" in path:
                return earned_badges
            if "available" in path:
                return available_badges
            return []

        with patch.object(garmin_client, "_get", side_effect=fake_get):
            return garmin_client.fetch_badge_updates("e@mail.com", "pass")

    def test_badge_ending_this_week_included(self, tmp_path, monkeypatch):
        badges = [_badge("This Week", end_offset_days=2)]
        result = self._run(badges, tmp_path=tmp_path, monkeypatch=monkeypatch)
        names = [b["badgeName"] for b in result["available_challenges"]]
        assert "This Week" in names

    def test_badge_with_null_end_date_excluded(self, tmp_path, monkeypatch):
        badges = [_badge("No End", end_offset_days=None)]
        result = self._run(badges, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert result["available_challenges"] == []

    def test_already_earned_badge_excluded(self, tmp_path, monkeypatch):
        badges = [_badge("Earned", end_offset_days=2, earned=True)]
        result = self._run(badges, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert result["available_challenges"] == []

    def test_badge_ending_after_this_week_excluded(self, tmp_path, monkeypatch):
        # End date is 10 days from now → beyond current Sunday
        now = datetime.now()
        far_future = (now + timedelta(days=10)).isoformat()
        badge = {
            "badgeName": "Future", "badgeChallengeId": "2",
            "earnedByMe": False, "badgeEndDate": far_future,
        }
        result = self._run([badge], tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert result["available_challenges"] == []

    def test_badge_ending_before_this_week_excluded(self, tmp_path, monkeypatch):
        # End date was last week
        past = (datetime.now() - timedelta(days=8)).isoformat()
        badge = {
            "badgeName": "Past", "badgeChallengeId": "3",
            "earnedByMe": False, "badgeEndDate": past,
        }
        result = self._run([badge], tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert result["available_challenges"] == []

    def test_multiple_badges_filtered_correctly(self, tmp_path, monkeypatch):
        badges = [
            _badge("Good", end_offset_days=1, badge_id="1"),
            _badge("No End", end_offset_days=None, badge_id="2"),
            _badge("Earned", end_offset_days=2, earned=True, badge_id="3"),
        ]
        result = self._run(badges, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert len(result["available_challenges"]) == 1
        assert result["available_challenges"][0]["badgeName"] == "Good"

    def test_newly_earned_detected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(garmin_client, "STATE_FILE", str(tmp_path / "state.json"))
        # Pre-seed state with no known earned badges
        garmin_client.save_state({"earned_badge_ids": [], "notified_challenge_ids": []})

        earned = [{"badgeName": "Shiny", "badgeId": "42"}]
        result = self._run([], earned_badges=earned, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert len(result["newly_earned"]) == 1
        assert result["newly_earned"][0]["badgeName"] == "Shiny"

    def test_already_known_earned_not_in_newly_earned(self, tmp_path, monkeypatch):
        monkeypatch.setattr(garmin_client, "STATE_FILE", str(tmp_path / "state.json"))
        garmin_client.save_state({"earned_badge_ids": ["42"], "notified_challenge_ids": []})

        earned = [{"badgeName": "Old Badge", "badgeId": "42"}]
        result = self._run([], earned_badges=earned, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert result["newly_earned"] == []

    def test_state_saved_after_fetch(self, tmp_path, monkeypatch):
        state_path = str(tmp_path / "state.json")
        monkeypatch.setattr(garmin_client, "STATE_FILE", state_path)
        monkeypatch.setattr(garmin_client, "_session", MagicMock())

        badges = [_badge("Good", end_offset_days=1, badge_id="77")]
        def side_effect(p):
            return badges if "available" in p else []

        with patch.object(garmin_client, "_get", side_effect=side_effect):
            garmin_client.fetch_badge_updates("e@mail.com", "pass")

        with open(state_path) as f:
            state = json.load(f)
        assert "77" in state["notified_challenge_ids"]

    def test_empty_response_returns_empty_lists(self, tmp_path, monkeypatch):
        result = self._run([], tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert result == {"newly_earned": [], "available_challenges": []}

    def test_api_failure_returns_empty_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(garmin_client, "STATE_FILE", str(tmp_path / "state.json"))
        monkeypatch.setattr(garmin_client, "_session", MagicMock())

        def boom(path):
            if "available" in path:
                raise RuntimeError("network error")
            return []

        with patch.object(garmin_client, "_get", side_effect=boom):
            result = garmin_client.fetch_badge_updates("e@mail.com", "pass")

        assert result["available_challenges"] == []


# ---------------------------------------------------------------------------
# _build_session
# ---------------------------------------------------------------------------

class TestBuildSession:
    def test_cookie_header_set(self):
        token_data = {
            "cookies": {"JWT_WEB": "abc123", "SESSIONID": "xyz"},
            "csrf_token": "tok",
        }
        session = garmin_client._build_session(token_data)
        assert "JWT_WEB=abc123" in session.headers["Cookie"]
        assert "SESSIONID=xyz" in session.headers["Cookie"]

    def test_csrf_header_set_when_present(self):
        token_data = {"cookies": {"JWT_WEB": "a"}, "csrf_token": "csrf-value"}
        session = garmin_client._build_session(token_data)
        assert session.headers["connect-csrf-token"] == "csrf-value"

    def test_csrf_header_absent_when_missing(self):
        token_data = {"cookies": {"JWT_WEB": "a"}, "csrf_token": None}
        session = garmin_client._build_session(token_data)
        assert "connect-csrf-token" not in session.headers

    def test_user_agent_set(self):
        token_data = {"cookies": {}, "csrf_token": None}
        session = garmin_client._build_session(token_data)
        assert "Mozilla" in session.headers["User-Agent"]
