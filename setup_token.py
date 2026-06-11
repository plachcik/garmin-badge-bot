"""
Run this ONCE to login to Garmin and save the session token.
Uses the web SSO flow to avoid mobile API rate limits.

Usage:
  python setup_token.py
"""
import os
import re
import json
import getpass
import requests
from dotenv import load_dotenv

load_dotenv()

email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ")
password = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")

TOKEN_FILE = "garmin_tokens.json"

SSO_BASE = "https://sso.garmin.com/sso"
CONNECT_URL = "https://connect.garmin.com/modern/"

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "origin": "https://sso.garmin.com",
    "referer": "https://sso.garmin.com/",
})

params = {
    "service": CONNECT_URL,
    "webhost": CONNECT_URL,
    "source": CONNECT_URL,
    "redirectAfterAccountLoginUrl": CONNECT_URL,
    "redirectAfterAccountCreationUrl": CONNECT_URL,
    "gauthHost": SSO_BASE,
    "locale": "en_US",
    "id": "gauth-widget",
    "clientId": "GarminConnect",
    "rememberMeShown": "true",
    "rememberMeChecked": "false",
    "createAccountShown": "true",
    "openCreateAccount": "false",
    "displayNameShown": "false",
    "consumeServiceTicket": "false",
    "initialFocus": "true",
    "embedWidget": "false",
    "generateExtraServiceTicket": "true",
    "generateTwoExtraServiceTickets": "false",
    "generateNoServiceTicket": "false",
    "globalOptInShown": "true",
    "globalOptInChecked": "false",
    "mobile": "false",
    "connectLegalTerms": "true",
    "locationPromptShown": "true",
    "showPassword": "true",
}

print("Step 1: Loading SSO page...")
resp = session.get(f"{SSO_BASE}/signin", params=params)
resp.raise_for_status()

csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)
if not csrf:
    raise RuntimeError("Could not find CSRF token. Garmin may have changed their login page.")
csrf_token = csrf.group(1)
print("         CSRF token found.")

print("Step 2: Submitting credentials...")
form_data = {
    "username": email,
    "password": password,
    "embed": "false",
    "_csrf": csrf_token,
}
resp = session.post(
    f"{SSO_BASE}/signin",
    params=params,
    data=form_data,
    allow_redirects=True,
)

ticket_match = re.search(r'ticket=([^&"]+)', resp.url) or re.search(r'ticket=([^&"]+)', resp.text)
if not ticket_match:
    if "Invalid credentials" in resp.text or "incorrectPassword" in resp.text:
        raise RuntimeError("❌ Invalid credentials — check your email and password.")
    raise RuntimeError(f"❌ Login failed — could not find ticket.\nURL: {resp.url}")

ticket = ticket_match.group(1)
print("         Service ticket obtained.")

print("Step 3: Exchanging ticket with Garmin Connect...")
resp = session.get(CONNECT_URL, params={"ticket": ticket}, allow_redirects=True)
resp.raise_for_status()

print("Step 4: Fetching CSRF token and session...")
session.headers.update({
    "NK": "NT",
    "origin": "https://connect.garmin.com",
    "referer": "https://connect.garmin.com/",
})
# Hit the modern app to get SESSIONID + csrf-token
csrf_resp = session.get("https://connect.garmin.com/modern/")
csrf_token = None
for pattern in [
    r'csrf[_-]token["\s:]+([0-9a-f-]{36})',
    r'"csrfToken"\s*:\s*"([^"]+)"',
    r'connect-csrf-token["\s:]+([0-9a-f-]{36})',
]:
    m = re.search(pattern, csrf_resp.text, re.IGNORECASE)
    if m:
        csrf_token = m.group(1)
        break

# Also try fetching it from a dedicated endpoint
if not csrf_token:
    try:
        ct_resp = session.get("https://connect.garmin.com/modern/garmin-api/user/csrf-token")
        if ct_resp.status_code == 200:
            csrf_token = ct_resp.json().get("token") or ct_resp.text.strip().strip('"')
    except Exception:
        pass

cookies = {c.name: c.value for c in session.cookies}
access_token = cookies.get("JWT_WEB")

print(f"         JWT token: {'✅' if access_token else '❌'}")
print(f"         CSRF token: {'✅ ' + csrf_token if csrf_token else '❌ not found'}")
print(f"         SESSIONID: {'✅' if cookies.get('SESSIONID') else '❌'}")

token_data = {
    "auth_type": "web_session",
    "cookies": cookies,
    "access_token": access_token,
    "csrf_token": csrf_token,
}

with open(TOKEN_FILE, "w") as f:
    json.dump(token_data, f, indent=2)

print(f"\n✅ Session saved to {TOKEN_FILE}")
print(f"   Cookies: {list(cookies.keys())}")
print(f"   JWT token: {'✅ yes' if access_token else '❌ missing — gc-api calls may fail'}")
print()
print("You can now run: python main.py")
