"""
One-time setup: log in via headless browser and save tokens.
Run this before starting main.py for the first time.

Usage:
  python setup_playwright.py
"""
import logging
import os

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
load_dotenv()

from garmin_auth import get_fresh_tokens  # noqa: E402 — must run after load_dotenv()

email = os.environ["GARMIN_EMAIL"]
password = os.environ["GARMIN_PASSWORD"]

data = get_fresh_tokens(email, password)
print("\n✅ Tokens saved!")
print(f"   JWT: {'✅' if data.get('access_token') else '❌'}")
print(f"   CSRF: {'✅ ' + data['csrf_token'] if data.get('csrf_token') else '❌'}")
print(f"   Cookies: {list(data['cookies'].keys())}")
print("\nRun: python main.py")
