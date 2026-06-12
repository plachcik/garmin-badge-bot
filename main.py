import logging
import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import garmin_client
from garmin_client import fetch_badge_updates, fetch_today_special_badges
from message_builder import build_daily_message, build_today_special_message
from subscribers import add_subscriber, load_subscribers

load_dotenv()

# Ensure persistent data directory exists
_DATA_DIR = os.environ.get("DATA_DIR", ".")
if _DATA_DIR != ".":
    os.makedirs(_DATA_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
# Suppress httpx request logs — they contain the bot token in the URL
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

GARMIN_EMAIL = os.environ["GARMIN_EMAIL"]
GARMIN_PASSWORD = os.environ["GARMIN_PASSWORD"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
DAILY_HOUR = int(os.getenv("DAILY_HOUR", "8"))
DAILY_MINUTE = int(os.getenv("DAILY_MINUTE", "0"))
WEEKLY_EVERY_DAY = os.getenv("WEEKLY_EVERY_DAY", "false").lower() == "true"
_POLAND_TZ = ZoneInfo("Europe/Warsaw")


def _utc_to_poland(hour: int, minute: int) -> tuple[int, int]:
    """Convert a UTC hour:minute to Europe/Warsaw local time (handles CET/CEST automatically)."""
    utc_dt = datetime.now(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    poland_dt = utc_dt.astimezone(_POLAND_TZ)
    return poland_dt.hour, poland_dt.minute


async def _send_to_chat(app: Application, chat_id: int, text: str) -> None:
    """Send a (potentially long) MarkdownV2 message to a single chat."""
    limit = 4000
    while text:
        chunk, text = text[:limit], text[limit:]
        await app.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")


async def _broadcast(app: Application, text: str) -> None:
    """Send a message to all subscribers. Falls back to TELEGRAM_CHAT_ID if none registered."""
    subscribers = load_subscribers()
    if not subscribers:
        subscribers = [TELEGRAM_CHAT_ID]
    for chat_id in subscribers:
        try:
            await _send_to_chat(app, chat_id, text)
        except Exception as e:
            logger.error("Failed to send to chat_id=%s: %s", chat_id, e)


_SCREENSHOT_NAMES = [
    "login_debug.png",
    "login_after_submit.png",
    "login_debug_timeout.png",
    "login_debug_nobutton.png",
]


async def _notify_admin_login_failure(app: Application, error: Exception) -> None:
    """Send login failure details + any saved screenshots to the admin (TELEGRAM_CHAT_ID)."""
    msg = f"🔐 Login to Garmin failed\n\n{error}"
    try:
        await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        logger.error("Failed to send admin failure message: %s", e)
        return

    for name in _SCREENSHOT_NAMES:
        path = os.path.join(_DATA_DIR, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as f:
                await app.bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=f, caption=name)
            logger.info("Sent screenshot %s to admin", name)
        except Exception as e:
            logger.warning("Failed to send screenshot %s: %s", name, e)


async def send_weekly_digest(app: Application):
    """Every Monday at 8 AM — all badges available this week."""
    garmin_client._refresh_failed = False  # reset so each scheduled run gets a fresh attempt
    logger.info("Running weekly badge digest... [triggered by: scheduler]")
    try:
        data = fetch_badge_updates(GARMIN_EMAIL, GARMIN_PASSWORD)
        msg = build_daily_message(data)
        await _broadcast(app, msg)
        logger.info("Weekly digest sent.")
    except Exception as e:
        logger.error("Failed to send weekly digest: %s", e)
        if garmin_client._refresh_failed:
            await _notify_admin_login_failure(app, e)
        else:
            await _broadcast(app, f"⚠️ Error fetching Garmin badges: {e}")


async def send_today_special(app: Application):
    """Every day at 8 AM — badges whose start and end share today's month+day."""
    logger.info("Running today-special badge check... [triggered by: scheduler]")
    try:
        badges = fetch_today_special_badges()
        if not badges:
            logger.info("No today-special badges for today.")
            return
        msg = build_today_special_message(badges)
        await _broadcast(app, msg)
        logger.info("Today-special message sent (%d badge(s)).", len(badges))
    except Exception as e:
        logger.error("Failed to send today-special badges: %s", e)
        if garmin_client._refresh_failed:
            await _notify_admin_login_failure(app, e)
        else:
            await _broadcast(app, f"⚠️ Error fetching today's special badges: {e}")


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info("Received subscribe command from chat_id=%s", chat_id)
    newly_added = add_subscriber(chat_id)
    if newly_added:
        logger.info("Subscribed new chat_id=%s to scheduled digests", chat_id)
        await update.message.reply_text(
            "✅ Zapisano! Będziesz otrzymywać powiadomienia o dostępnych odznakach.\n\n"
            "Komendy:\n"
            "/odznaki — sprawdź odznaki teraz\n"
            "/subscribe lub /dawaj_odznaki — zapisz się na powiadomienia"
        )
    else:
        await update.message.reply_text(
            "👍 Już jesteś zapisany na powiadomienia!\n\n"
            "Komendy:\n"
            "/odznaki — sprawdź odznaki teraz\n"
            "/subscribe lub /dawaj_odznaki — zapisz się na powiadomienia"
        )


async def debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received update: %s", update)


async def send_long_message(send_fn, text: str, parse_mode="MarkdownV2"):
    """Split a long message into ≤4096-char chunks and send each."""
    limit = 4000
    while text:
        chunk, text = text[:limit], text[limit:]
        await send_fn(chunk, parse_mode=parse_mode)


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(
        "Badge check triggered by user: %s (id=%s)", user.username or user.first_name, user.id
    )
    garmin_client._refresh_failed = False  # always attempt fresh login on manual check
    await update.message.reply_text("⏳ Sprawdzam odznaki\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        # Weekly badges
        data = fetch_badge_updates(GARMIN_EMAIL, GARMIN_PASSWORD)
        msg = build_daily_message(data, header="👋🏻 *Dostępne odznaki w tym tygodniu:*")
        await send_long_message(update.message.reply_text, msg)

        # Today-special badges — silent if none found
        today_badges = fetch_today_special_badges()
        if today_badges:
            today_msg = build_today_special_message(today_badges)
            await send_long_message(update.message.reply_text, today_msg)
    except Exception as e:
        logger.error("cmd_check error: %s", e)
        await update.message.reply_text(f"⚠️ Error: {e}")
        if garmin_client._refresh_failed:
            await _notify_admin_login_failure(context.application, e)


def _startup_login() -> None:
    """Ensure a valid Garmin session exists before the bot starts polling."""
    import concurrent.futures

    from garmin_auth import get_fresh_tokens
    from garmin_client import TOKEN_FILE, _get, get_session

    # First-time setup: no token file at all
    if not os.path.exists(TOKEN_FILE):
        logger.info("No token file found — running first-time Playwright login...")
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(get_fresh_tokens, GARMIN_EMAIL, GARMIN_PASSWORD).result(timeout=120)
            logger.info("First-time login complete.")
        except Exception as e:
            logger.error("First-time login failed: %s", e)
            return

    # Load the session from the token file
    try:
        get_session()
    except Exception as e:
        logger.error("Failed to load Garmin session: %s", e)
        return

    # Probe the API — if the saved token is expired, refresh right now
    logger.info("Probing Garmin API to verify session...")
    try:
        _get("/gc-api/badge-service/badge/available")
        logger.info("Garmin session is valid ✅")
    except Exception as e:
        logger.warning("Session probe failed (%s) — refreshing via Playwright...", e)
        garmin_client._refresh_failed = False
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(get_fresh_tokens, GARMIN_EMAIL, GARMIN_PASSWORD).result(timeout=120)
            logger.info("Startup Playwright login complete ✅")
            # Rebuild the session with the new tokens
            garmin_client._session = None
            get_session()
        except Exception as refresh_err:
            logger.error("Startup Playwright login failed: %s", refresh_err)


def main():
    _startup_login()

    scheduler = AsyncIOScheduler()

    async def on_startup(application):
        # Weekly digest — every Monday at 8 AM UTC (or every day if WEEKLY_EVERY_DAY=true)
        weekly_kwargs = {"hour": DAILY_HOUR, "minute": DAILY_MINUTE}
        if not WEEKLY_EVERY_DAY:
            weekly_kwargs["day_of_week"] = "mon"
        scheduler.add_job(send_weekly_digest, trigger="cron", args=[application], **weekly_kwargs)
        ph, pm = _utc_to_poland(DAILY_HOUR, DAILY_MINUTE)
        logger.info(
            "Weekly digest scheduled: %s at %02d:%02d UTC = %02d:%02d Poland time",
            "every day" if WEEKLY_EVERY_DAY else "Mondays only",
            DAILY_HOUR, DAILY_MINUTE, ph, pm,
        )

        # Today-special check — 1 minute after weekly digest to avoid overlap
        special_minute = (DAILY_MINUTE + 1) % 60
        special_hour = DAILY_HOUR + (1 if DAILY_MINUTE == 59 else 0)
        scheduler.add_job(
            send_today_special,
            trigger="cron",
            hour=special_hour,
            minute=special_minute,
            args=[application],
        )

        scheduler.start()

        # Log all current subscribers with their display names
        subscribers = load_subscribers()
        if subscribers:
            logger.info("Subscribers (%d):", len(subscribers))
            for chat_id in subscribers:
                try:
                    chat = await application.bot.get_chat(chat_id)
                    display = chat.title or chat.full_name or str(chat_id)
                    if chat.username:
                        display = f"{display} (@{chat.username})"
                    name = display
                    logger.info("  • %s (id=%s)", name, chat_id)
                except Exception as e:
                    logger.info("  • [unknown] (id=%s) — %s", chat_id, e)
        else:
            logger.info("No subscribers yet — will fall back to TELEGRAM_CHAT_ID=%s", TELEGRAM_CHAT_ID)

        ph, pm = _utc_to_poland(DAILY_HOUR, DAILY_MINUTE)
        sph, spm = _utc_to_poland(special_hour, special_minute)
        logger.info(
            "Scheduler started — weekly digest %s at %02d:%02d UTC = %02d:%02d Poland time,"
            " today-special at %02d:%02d UTC = %02d:%02d Poland time",
            "every day" if WEEKLY_EVERY_DAY else "Mondays only",
            DAILY_HOUR, DAILY_MINUTE, ph, pm,
            special_hour, special_minute, sph, spm,
        )

    async def on_shutdown(application):
        scheduler.shutdown()

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_subscribe))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("dawaj_odznaki", cmd_subscribe))
    app.add_handler(CommandHandler("odznaki", cmd_check))
    app.add_handler(MessageHandler(filters.ALL, debug_handler))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
