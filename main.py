import logging
import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from garmin_client import fetch_badge_updates, fetch_today_special_badges
from message_builder import build_daily_message, build_today_special_message

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


async def _send_to_chat(app: Application, text: str):
    """Send a (potentially long) MarkdownV2 message to the configured chat."""
    limit = 4000
    while text:
        chunk, text = text[:limit], text[limit:]
        await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=chunk, parse_mode="MarkdownV2"
        )


async def send_weekly_digest(app: Application):
    """Every Monday at 8 AM — all badges available this week."""
    logger.info("Running weekly badge digest... [triggered by: scheduler]")
    try:
        data = fetch_badge_updates(GARMIN_EMAIL, GARMIN_PASSWORD)
        msg = build_daily_message(data)
        await _send_to_chat(app, msg)
        logger.info("Weekly digest sent.")
    except Exception as e:
        logger.error("Failed to send weekly digest: %s", e)
        await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"⚠️ Error fetching Garmin badges: {e}",
        )


async def send_today_special(app: Application):
    """Every day at 8 AM — badges whose start and end share today's month+day."""
    logger.info("Running today-special badge check... [triggered by: scheduler]")
    try:
        badges = fetch_today_special_badges()
        if not badges:
            logger.info("No today-special badges for today.")
            return
        msg = build_today_special_message(badges)
        await _send_to_chat(app, msg)
        logger.info("Today-special message sent (%d badge(s)).", len(badges))
    except Exception as e:
        logger.error("Failed to send today-special badges: %s", e)
        await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"⚠️ Error fetching today's special badges: {e}",
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info("Received /start from chat_id=%s", chat_id)
    await update.message.reply_text(
        f"👋 Garmin Badge Bot is running!\n\n"
        f"Your chat ID: {chat_id}\n\n"
        f"Komendy:\n"
        f"/odznaki — sprawdź odznaki teraz\n"
        f"/start — pokaż tę wiadomość"
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


def main():
    # Pre-load Garmin session before starting the bot
    from garmin_client import TOKEN_FILE, get_session
    if not os.path.exists(TOKEN_FILE):
        logger.info("No token file found — running first-time Playwright login...")
        import concurrent.futures

        from garmin_auth import get_fresh_tokens
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(get_fresh_tokens, GARMIN_EMAIL, GARMIN_PASSWORD).result(timeout=120)
            logger.info("First-time login complete.")
        except Exception as e:
            logger.error("First-time login failed: %s", e)
    try:
        get_session()
    except Exception as e:
        logger.warning("Garmin session pre-load failed: %s", e)

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

        # Today-special check — every day at 8 AM UTC
        scheduler.add_job(
            send_today_special,
            trigger="cron",
            hour=DAILY_HOUR,
            minute=DAILY_MINUTE,
            args=[application],
        )

        scheduler.start()
        ph, pm = _utc_to_poland(DAILY_HOUR, DAILY_MINUTE)
        logger.info(
            "Scheduler started — weekly digest %s + today-special check every day"
            " at %02d:%02d UTC = %02d:%02d Poland time",
            "every day" if WEEKLY_EVERY_DAY else "Mondays only",
            DAILY_HOUR, DAILY_MINUTE, ph, pm,
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

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("odznaki", cmd_check))
    app.add_handler(MessageHandler(filters.ALL, debug_handler))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
