"""
Headless browser login to Garmin Connect using Playwright.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("DATA_DIR", ".")
TOKEN_FILE = os.path.join(_DATA_DIR, "garmin_tokens.json")
CONNECT_URL = "https://connect.garmin.com/modern/"


def get_fresh_tokens(email: str, password: str) -> dict:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    logger.info("Launching headless browser to log in to Garmin Connect...")

    with sync_playwright() as pw:
        browser = pw.firefox.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) "
                "Gecko/20100101 Firefox/124.0"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = context.new_page()

        logger.info("Navigating to Garmin Connect (will redirect to SSO)...")
        page.goto(CONNECT_URL, timeout=30000)

        # Wait until we land on the SSO signin page
        try:
            page.wait_for_url("**/sso.garmin.com/**", timeout=15000)
            logger.info("Redirected to SSO page: %s", page.url)
        except PWTimeout:
            logger.info("No SSO redirect — current URL: %s", page.url)

        # Fill login form (Garmin SSO page)
        try:
            email_sel = (
                "#username, input[name='username'], input[type='email'], input[name='email']"
            )
            page.wait_for_selector(email_sel, timeout=10000)
            logger.info("Login form found, filling credentials...")

            # Use type() instead of fill() so React detects the change events
            page.click(email_sel)
            page.type(email_sel, email, delay=50)

            pass_sel = "#password, input[name='password'], input[type='password']"
            page.click(pass_sel)
            page.type(pass_sel, password, delay=50)

            # Take screenshot to debug if needed
            page.screenshot(path="login_debug.png")
            logger.info("Screenshot saved to login_debug.png")

            # Try multiple submit button patterns
            submitted = False
            for btn_sel in [
                "#login-btn-signin",
                "button[data-testid='login-submit-btn']",
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Sign In')",
                "button:has-text('Log In')",
                "button:has-text('Continue')",
                "button:has-text('Zaloguj')",
                "button:has-text('Dalej')",
                "button:has-text('Next')",
            ]:
                try:
                    if page.locator(btn_sel).count() > 0:
                        page.click(btn_sel)
                        logger.info("Clicked submit with selector: %s", btn_sel)
                        submitted = True
                        break
                except Exception:
                    continue

            if not submitted:
                # Try pressing Enter on the password field
                try:
                    page.press(pass_sel, "Enter")
                    logger.info("Submitted form via Enter key")
                    submitted = True
                except Exception:
                    pass

            if not submitted:
                # Last resort — click the first visible button on the page
                try:
                    buttons = page.locator("button").all()
                    logger.info("Buttons found on page: %d", len(buttons))
                    for btn in buttons:
                        if btn.is_visible():
                            logger.info("Clicking visible button: %s", btn.inner_text())
                            btn.click()
                            submitted = True
                            break
                except Exception as e:
                    logger.warning("Last-resort button click failed: %s", e)

            if not submitted:
                page.screenshot(path="login_debug_nobutton.png")
                raise RuntimeError("Could not find submit button")

        except PWTimeout:
            page.screenshot(path="login_debug_timeout.png")
            logger.error("Login form not found on: %s", page.url)
            browser.close()
            raise RuntimeError(f"Login form not found at {page.url}")

        # Wait for redirect back to connect.garmin.com
        logger.info("Waiting for redirect back to Garmin Connect...")
        try:
            page.wait_for_url("**/connect.garmin.com/**", timeout=20000)
        except PWTimeout:
            page.screenshot(path="login_after_submit.png")
            logger.warning("Did not redirect to connect.garmin.com — current: %s", page.url)
            logger.warning("Screenshot saved to login_after_submit.png")

        page.wait_for_load_state("networkidle", timeout=20000)
        logger.info("Landed on: %s", page.url)

        # Intercept a real gc-api call made by the app to capture the CSRF token
        csrf_token = None
        captured = {}

        def handle_request(request):
            if "gc-api" in request.url and request.headers.get("connect-csrf-token"):
                captured["csrf"] = request.headers["connect-csrf-token"]

        page.on("request", handle_request)

        # Navigate to badges page to trigger the app to make badge API calls
        import contextlib
        with contextlib.suppress(Exception):
            page.goto(
                "https://connect.garmin.com/modern/challenges",
                timeout=20000,
                wait_until="networkidle",
            )

        csrf_token = captured.get("csrf")
        if csrf_token:
            logger.info("CSRF token captured from network: %s", csrf_token)
        else:
            # Fallback: try fetching it via JS with all cookies present
            try:
                result = page.evaluate("""async () => {
                    const r = await fetch('/gc-api/badge-service/badge/available', {
                        credentials: 'include'
                    });
                    return { status: r.status };
                }""")
                logger.info("In-browser API call status: %s", result.get("status"))
            except Exception as e:
                logger.warning("In-browser fetch failed: %s", e)

        # Extract all cookies
        cookies_list = context.cookies(["https://connect.garmin.com", "https://sso.garmin.com"])
        cookies = {c["name"]: c["value"] for c in cookies_list}
        browser.close()

    jwt = cookies.get("JWT_WEB")
    session_id = cookies.get("SESSIONID")
    logger.info("Tokens extracted — JWT: %s, SESSIONID: %s, CSRF: %s",
                "✅" if jwt else "❌",
                "✅" if session_id else "❌",
                "✅" if csrf_token else "❌")

    if not jwt:
        raise RuntimeError("Login appeared to succeed but no JWT_WEB cookie found.")

    token_data = {
        "auth_type": "web_session",
        "cookies": cookies,
        "access_token": jwt,
        "csrf_token": csrf_token,
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    return token_data
