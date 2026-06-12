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
SSO_URL = (
    "https://sso.garmin.com/portal/sso/en-US/sign-in"
    "?clientId=GarminConnect&service=https%3A%2F%2Fconnect.garmin.com%2Fapp"
)


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

        # Navigate directly to the SSO sign-in page (known-good URL with correct service param)
        logger.info("Navigating directly to SSO sign-in page...")
        page.goto(SSO_URL, timeout=30000)

        # Let the SPA fully render
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            logger.info("networkidle timeout — proceeding anyway")
        logger.info("SSO page loaded: %s", page.url)

        # Fill login form
        try:
            email_sel = (
                "#username, input[name='username'], input[type='email'], input[name='email']"
            )
            page.wait_for_selector(email_sel, timeout=20000)
            logger.info("Login form found, filling credentials...")

            pass_sel = "#password, input[name='password'], input[type='password']"

            # Use React's native input setter — this triggers the synthetic onChange that
            # controlled inputs listen to, which is what enables the submit button.
            page.evaluate(
                """([emailVal, passVal, emailSel, passSel]) => {
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    const fire = (el, val) => {
                        setter.call(el, val);
                        el.dispatchEvent(new Event('input',  { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    };
                    const emailEl = document.querySelector(emailSel);
                    const passEl  = document.querySelector(passSel);
                    if (emailEl) fire(emailEl, emailVal);
                    if (passEl)  fire(passEl,  passVal);
                }""",
                [email, password, "#username,input[name='username'],input[type='email']",
                 "#password,input[name='password'],input[type='password']"],
            )
            logger.info("Credentials set via React native setter")

            # Poll for the submit button to become enabled (up to 5 s)
            import contextlib
            submit_btn = None
            _SUBMIT_TEXTS = {"sign in", "log in", "continue", "zaloguj", "dalej", "next"}
            for attempt in range(10):
                page.wait_for_timeout(500)
                for btn in page.locator("button").all():
                    with contextlib.suppress(Exception):
                        if btn.is_visible() and (
                            btn.get_attribute("type") == "submit"
                            or btn.inner_text().strip().lower() in _SUBMIT_TEXTS
                        ):
                            submit_btn = btn
                            break
                if submit_btn is not None and submit_btn.is_enabled():
                    logger.info("Submit button enabled after %d × 500ms", attempt + 1)
                    break
                submit_btn = None  # keep polling if still disabled

            # Screenshot before submit — saved to DATA_DIR (persists on Railway volume)
            _screenshot(page, "login_debug.png")

            submitted = False
            if submit_btn is not None:
                logger.info("Clicking submit button (force=True)")
                submit_btn.click(force=True)
                submitted = True
            else:
                # Button never became enabled — press Enter as last resort
                logger.info("Submit button stayed disabled after 5s — pressing Enter on password field")
                page.press(pass_sel, "Enter")
                submitted = True

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
