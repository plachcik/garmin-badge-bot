import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from garmin_client import fetch_badge_updates
from message_builder import build_daily_message

load_dotenv()
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


async def send_daily_digest(app: Application):
    logger.info("Running daily badge check...")
    try:
        data = fetch_badge_updates(GARMIN_EMAIL, GARMIN_PASSWORD)
        msg = build_daily_message(data)
        limit = 4000
        while msg:
            chunk, msg = msg[:limit], msg[limit:]
            await app.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID, text=chunk, parse_mode="MarkdownV2"
            )
        logger.info("Daily digest sent.")
    except Exception as e:
        logger.error("Failed to send daily digest: %s", e)
        await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"⚠️ Error fetching Garmin badges: {e}",
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info("Received /start from chat_id=%s", chat_id)
    await update.message.reply_text(
        f"👋 Garmin Badge Bot is running!\n\n"
        f"Your chat ID: {chat_id}\n\n"
        f"Commands:\n"
        f"/check — run badge check now\n"
        f"/start — show this message"
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
        data = fetch_badge_updates(GARMIN_EMAIL, GARMIN_PASSWORD)
        msg = build_daily_message(data)
        await send_long_message(update.message.reply_text, msg)
    except Exception as e:
        logger.error("cmd_check error: %s", e)
        await update.message.reply_text(f"⚠️ Error: {e}")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(MessageHandler(filters.ALL, debug_handler))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour=DAILY_HOUR,
        minute=DAILY_MINUTE,
        args=[app],
    )
    scheduler.start()
    logger.info("Scheduler started — daily digest at %02d:%02d UTC", DAILY_HOUR, DAILY_MINUTE)

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
