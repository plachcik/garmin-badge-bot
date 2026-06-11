"""
Extract Garmin auth tokens directly from a browser curl command.

How to get the curl command:
  1. Open https://connect.garmin.com in Chrome and log in
  2. Open DevTools (F12) → Network tab
  3. Refresh the page, find any request to connect.garmin.com/gc-api/...
  4. Right-click it → Copy → Copy as cURL
  5. Paste it when prompted below (then press Enter twice)

Usage:
  python setup_from_curl.py
"""
import re
import json

TOKEN_FILE = "garmin_tokens.json"

CURL_FILE = "curl.txt"

import os
if not os.path.exists(CURL_FILE):
    print(f"Please paste your curl command into a file called '{CURL_FILE}' in this folder, then run this script again.")
    print()
    print("How to get it:")
    print("  1. Open https://connect.garmin.com in Chrome and log in")
    print("  2. Open DevTools (F12) → Network tab")
    print("  3. Find any request to gc-api/badge-service/...")
    print("  4. Right-click → Copy → Copy as cURL")
    print(f"  5. Paste into {CURL_FILE} and save")
    exit(0)

with open(CURL_FILE) as f:
    curl = f.read()

# Extract cookies from -b '...'
cookies = {}
cookie_match = re.search(r"-b '([^']+)'", curl) or re.search(r'-b "([^"]+)"', curl)
if cookie_match:
    for part in cookie_match.group(1).split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()

# Extract headers from -H '...'
headers = {}
for m in re.finditer(r"-H '([^']+)'", curl):
    header = m.group(1)
    if ": " in header:
        k, v = header.split(": ", 1)
        headers[k.lower()] = v

csrf_token = headers.get("connect-csrf-token")
access_token = cookies.get("JWT_WEB")

if not cookies:
    print("❌ Could not parse cookies. Make sure you pasted the full curl command.")
    exit(1)

token_data = {
    "auth_type": "web_session",
    "cookies": cookies,
    "access_token": access_token,
    "csrf_token": csrf_token,
}

with open(TOKEN_FILE, "w") as f:
    json.dump(token_data, f, indent=2)

print(f"\n✅ Saved to {TOKEN_FILE}")
print(f"   Cookies captured: {list(cookies.keys())}")
print(f"   JWT token:        {'✅' if access_token else '❌ missing'}")
print(f"   CSRF token:       {'✅ ' + csrf_token if csrf_token else '❌ missing'}")
print(f"   SESSIONID:        {'✅' if cookies.get('SESSIONID') else '❌ missing'}")
print()
print("Run: python main.py")
