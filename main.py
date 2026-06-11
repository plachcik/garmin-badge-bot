import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from garmin_client import fetch_badge_updates, fetch_today_special_badges
from message_builder import build_daily_message, build_today_special_message

load_dotenv()

# Ensure persistent data directory exists (Railway volume at /app/data)
_DATA_DIR = os.environ.get("DATA_DIR", ".")
if _DATA_DIR != ".":
    os.makedirs(_DATA_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

GARMIN_EMAIL = os.environ["GARMIN_EMAIL"]
GARMIN_PASSWORD = os.environ["GARMIN_PASSWORD"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
DAILY_HOUR = int(os.getenv("DAILY_HOUR", "8"))
DAILY_MINUTE = int(os.getenv("DAILY_MINUTE", "0"))


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
    logger.info("Running weekly badge digest...")
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
    logger.info("Running today-special badge check...")
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
    await update.message.reply_text("⏳ Sprawdzam odznaki\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        # Weekly badges
        data = fetch_badge_updates(GARMIN_EMAIL, GARMIN_PASSWORD)
        msg = build_daily_message(data)
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
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("odznaki", cmd_check))
    app.add_handler(MessageHandler(filters.ALL, debug_handler))

    scheduler = AsyncIOScheduler()

    # Weekly digest — every Monday at 8 AM UTC
    scheduler.add_job(
        send_weekly_digest,
        trigger="cron",
        day_of_week="mon",
        hour=DAILY_HOUR,
        minute=DAILY_MINUTE,
        args=[app],
    )

    # Today-special check — every day at 8 AM UTC (fires only when there are matches)
    scheduler.add_job(
        send_today_special,
        trigger="cron",
        hour=DAILY_HOUR,
        minute=DAILY_MINUTE,
        args=[app],
    )

    scheduler.start()
    logger.info(
        "Scheduler started — weekly digest Mon %02d:%02d UTC, "
        "today-special check every day %02d:%02d UTC",
        DAILY_HOUR, DAILY_MINUTE, DAILY_HOUR, DAILY_MINUTE,
    )

    # Pre-load Garmin session on startup — run Playwright login if no token file yet
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

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
