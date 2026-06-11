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


def _screenshot(page, name: str) -> str:
    """Save a screenshot to DATA_DIR and return the path."""
    path = os.path.join(_DATA_DIR, name)
    try:
        page.screenshot(path=path)
        logger.info("Screenshot saved: %s", path)
    except Exception as e:
        logger.warning("Could not save screenshot %s: %s", path, e)
    return path


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

            # Screenshot before submit — saved to DATA_DIR (persists on Railway volume)
            _screenshot(page, "login_debug.png")

            # Log every button on the page so we know what's available
            try:
                all_buttons = page.locator("button").all()
                logger.info("Buttons on page (%d):", len(all_buttons))
                for i, btn in enumerate(all_buttons):
                    try:
                        logger.info(
                            "  [%d] visible=%s text=%r type=%r id=%r",
                            i,
                            btn.is_visible(),
                            btn.inner_text(),
                            btn.get_attribute("type"),
                            btn.get_attribute("id"),
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("Could not enumerate buttons: %s", e)

            # Also log the page HTML around the form (first 3000 chars)
            try:
                html = page.content()
                logger.info("Page HTML snippet:\n%s", html[:3000])
            except Exception:
                pass

            # Wait for the submit button to be visible and click it
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
                    locator = page.locator(btn_sel)
                    locator.wait_for(state="visible", timeout=3000)
                    locator.click()
                    logger.info("Clicked submit with selector: %s", btn_sel)
                    submitted = True
                    break
                except Exception:
                    continue

            if not submitted:
                # Last resort — click the first visible button on the page
                try:
                    buttons = page.locator("button").all()
                    for btn in buttons:
                        if btn.is_visible():
                            logger.info("Last-resort click: %r", btn.inner_text())
                            btn.click()
                            submitted = True
                            break
                except Exception as e:
                    logger.warning("Last-resort button click failed: %s", e)

            if not submitted:
                _screenshot(page, "login_debug_nobutton.png")
                raise RuntimeError("Could not find submit button")

        except PWTimeout:
            _screenshot(page, "login_debug_timeout.png")
            logger.error("Login form not found on: %s", page.url)
            browser.close()
            raise RuntimeError(f"Login form not found at {page.url}")

        # Wait for redirect back to connect.garmin.com
        logger.info("Waiting for redirect back to Garmin Connect...")
        try:
            page.wait_for_url("**/connect.garmin.com/**", timeout=20000)
        except PWTimeout:
            _screenshot(page, "login_after_submit.png")
            logger.warning("Did not redirect to connect.garmin.com — current: %s", page.url)

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
