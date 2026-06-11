import logging
import json
import os
import re
import requests

logger = logging.getLogger(__name__)

STATE_FILE = "garmin_state.json"
TOKEN_FILE = "garmin_tokens.json"

CONNECT_API = "https://connect.garmin.com"
SSO_BASE = "https://sso.garmin.com/sso"
CONNECT_MODERN = "https://connect.garmin.com/modern/"

_session: requests.Session | None = None
_token_data: dict = {}


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"earned_badge_ids": [], "notified_challenge_ids": []}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _build_session(token_data: dict) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "Referer": "https://connect.garmin.com/modern/",
        "origin": "https://connect.garmin.com",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    })
    cookie_str = "; ".join(f"{k}={v}" for k, v in token_data["cookies"].items())
    session.headers["Cookie"] = cookie_str
    csrf_token = token_data.get("csrf_token")
    if csrf_token:
        session.headers["connect-csrf-token"] = csrf_token
    return session


def _refresh_jwt(token_data: dict) -> bool:
    """Use Playwright headless browser (in a thread) to get a fresh session."""
    import os as _os
    import concurrent.futures
    from garmin_auth import get_fresh_tokens
    email = _os.getenv("GARMIN_EMAIL")
    password = _os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        logger.error("GARMIN_EMAIL/PASSWORD not set — cannot auto-refresh.")
        return False
    try:
        # Run sync Playwright in a thread to avoid asyncio conflict
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(get_fresh_tokens, email, password)
            new_data = future.result(timeout=60)
        token_data.update(new_data)
        return bool(new_data.get("access_token"))
    except Exception as e:
        logger.error("Playwright refresh failed: %s", e)
        return False


def get_session() -> requests.Session:
    global _session, _token_data

    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError("No token file found. Run: python setup_from_curl.py")

    with open(TOKEN_FILE) as f:
        _token_data = json.load(f)

    if _token_data.get("auth_type") != "web_session":
        raise RuntimeError("Old token format. Run: python setup_from_curl.py")

    _session = _build_session(_token_data)
    logger.info("Garmin: session loaded from %s", TOKEN_FILE)
    return _session


def _get(path: str) -> dict | list:
    global _session, _token_data
    if _session is None:
        get_session()

    url = f"{CONNECT_API}{path}"
    resp = _session.get(url)

    if resp.status_code in (401, 403):
        logger.warning("Got %s — attempting token refresh...", resp.status_code)
        if _refresh_jwt(_token_data):
            _session = _build_session(_token_data)
            resp = _session.get(url)
        else:
            logger.error("Refresh failed. Response body: %s", resp.text[:300])

    resp.raise_for_status()
    return resp.json()


def fetch_badge_updates(email: str, password: str) -> dict:
    if _session is None:
        get_session()

    state = load_state()

    # --- Earned badges ---
    try:
        earned_raw = _get("/gc-api/badge-service/badge/earned")
        earned_badges = earned_raw if isinstance(earned_raw, list) else earned_raw.get("badgeList", [])
    except Exception as e:
        logger.error("Failed to fetch earned badges: %s", e)
        earned_badges = []

    known_ids = set(state["earned_badge_ids"])
    newly_earned = [b for b in earned_badges if str(b.get("badgeId", "")) not in known_ids]
    state["earned_badge_ids"] = [str(b.get("badgeId", "")) for b in earned_badges]

    # --- Available badges ---
    try:
        challenges_raw = _get("/gc-api/badge-service/badge/available")
        challenges = challenges_raw if isinstance(challenges_raw, list) else challenges_raw.get("badgeList", [])
    except Exception as e:
        logger.warning("Failed to fetch available badges: %s", e)
        challenges = []

    from datetime import datetime, timedelta
    now = datetime.now()
    week_monday = now - timedelta(days=now.weekday())  # Monday 00:00
    week_monday = week_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_sunday = week_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    available_challenges = []
    new_challenge_ids = []

    for c in challenges:
        cid = str(c.get("badgeChallengeId") or c.get("badgeId", ""))
        earned_flag = c.get("earnedByMe") or c.get("badgeEarned") or c.get("earned", False)
        if earned_flag:
            continue

        end_str = c.get("badgeEndDate")
        start_str = c.get("badgeStartDate", "")

        # Skip badges with no end date
        if not end_str:
            continue

        try:
            end_dt = datetime.fromisoformat(end_str.rstrip("0").rstrip("."))
            start_dt = datetime.fromisoformat(start_str.rstrip("0").rstrip(".")) if start_str else week_monday
        except Exception:
            continue

        # Badge must end within this week (Mon–Sun)
        if end_dt <= week_sunday and end_dt >= week_monday:
            available_challenges.append(c)
            new_challenge_ids.append(cid)

    state["notified_challenge_ids"] = new_challenge_ids
    save_state(state)

    return {
        "newly_earned": newly_earned,
        "available_challenges": available_challenges,
    }
