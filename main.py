import logging
import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from garmin_client import fetch_badge_updates, fetch_today_special_badges
from message_builder import (
    badge_caption,
    badge_image_url,
    build_daily_message,
    today_special_header,
    weekly_digest_header,
)
from subscribers import add_subscriber, load_subscribers, save_subscriber_name

load_dotenv()

# Ensure persistent data directory exists
_DATA_DIR = os.environ.get("DATA_DIR", ".")
if _DATA_DIR != ".":
    os.makedirs(_DATA_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_TELEGRAM_CHAT_ID = int(os.environ["ADMIN_TELEGRAM_CHAT_ID"])
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
    """Send a message to all subscribers. Falls back to ADMIN_TELEGRAM_CHAT_ID if none."""
    subscribers = load_subscribers()
    if not subscribers:
        subscribers = [ADMIN_TELEGRAM_CHAT_ID]
    for chat_id in subscribers:
        try:
            await _send_to_chat(app, chat_id, text)
        except Exception as e:
            logger.error("Failed to send to chat_id=%s: %s", chat_id, e)


async def _broadcast_badges(
    app: Application,
    header: str,
    badges: list[dict],
    today_only: bool = False,
) -> None:
    """Send header text then one photo-per-badge to all subscribers."""
    subscribers = load_subscribers() or [ADMIN_TELEGRAM_CHAT_ID]
    for chat_id in subscribers:
        try:
            await app.bot.send_message(chat_id=chat_id, text=header, parse_mode="MarkdownV2")
            for badge in badges:
                caption = badge_caption(badge, today_only=today_only)
                url = badge_image_url(badge)
                try:
                    if url:
                        await app.bot.send_photo(
                            chat_id=chat_id, photo=url,
                            caption=caption, parse_mode="MarkdownV2",
                        )
                    else:
                        await app.bot.send_message(
                            chat_id=chat_id, text=caption, parse_mode="MarkdownV2",
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to send badge photo to %s: %s — falling back to text", chat_id, e
                    )
                    await app.bot.send_message(
                        chat_id=chat_id, text=caption, parse_mode="MarkdownV2",
                    )
        except Exception as e:
            logger.error("Failed to send to chat_id=%s: %s", chat_id, e)


async def _notify_admin_error(app: Application, error: Exception) -> None:
    """Send an API failure notice to the admin chat (ADMIN_TELEGRAM_CHAT_ID)."""
    msg = f"⚠️ Garmin badges API error\n\n{error}"
    try:
        await app.bot.send_message(chat_id=ADMIN_TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        logger.error("Failed to send admin error notification: %s", e)


async def send_weekly_digest(app: Application):
    """Every Monday at 8 AM — all badges available this week."""
    logger.info("Running weekly badge digest... [triggered by: scheduler]")
    try:
        data = fetch_badge_updates()
        available = data.get("available_challenges", [])
        if not available:
            await _broadcast(app, build_daily_message(data))
        else:
            await _broadcast_badges(app, weekly_digest_header(), available)
        logger.info("Weekly digest sent.")
    except Exception as e:
        logger.error("Failed to send weekly digest: %s", e)
        await _notify_admin_error(app, e)


async def send_today_special(app: Application):
    """Every day — badges whose start and end share today's month+day."""
    logger.info("Running today-special badge check... [triggered by: scheduler]")
    try:
        badges = fetch_today_special_badges()
        if not badges:
            logger.info("No today-special badges for today.")
            return
        await _broadcast_badges(app, today_special_header(), badges, today_only=True)
        logger.info("Today-special message sent (%d badge(s)).", len(badges))
    except Exception as e:
        logger.error("Failed to send today-special badges: %s", e)
        await _notify_admin_error(app, e)


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info("Received subscribe command from chat_id=%s", chat_id)
    newly_added = add_subscriber(chat_id)
    if newly_added:
        chat = await context.bot.get_chat(chat_id)
        display = chat.title or chat.full_name or str(chat_id)
        if chat.username:
            display = f"{display} (@{chat.username})"
        save_subscriber_name(chat_id, display)
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
    await update.message.reply_text("⏳ Sprawdzam odznaki\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        data = fetch_badge_updates()
        available = data.get("available_challenges", [])
        if not available:
            await send_long_message(
                update.message.reply_text,
                build_daily_message(data, header="👋🏻 *Dostępne odznaki w tym tygodniu:*"),
            )
        else:
            await update.message.reply_text(
                weekly_digest_header("👋🏻 *Dostępne odznaki w tym tygodniu:*"),
                parse_mode="MarkdownV2",
            )
            for badge in available:
                caption = badge_caption(badge)
                url = badge_image_url(badge)
                try:
                    if url:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id, photo=url,
                            caption=caption, parse_mode="MarkdownV2",
                        )
                    else:
                        await update.message.reply_text(caption, parse_mode="MarkdownV2")
                except Exception:
                    await update.message.reply_text(caption, parse_mode="MarkdownV2")

        today_badges = fetch_today_special_badges()
        if today_badges:
            await update.message.reply_text(today_special_header(), parse_mode="MarkdownV2")
            for badge in today_badges:
                caption = badge_caption(badge, today_only=True)
                url = badge_image_url(badge)
                try:
                    if url:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id, photo=url,
                            caption=caption, parse_mode="MarkdownV2",
                        )
                    else:
                        await update.message.reply_text(caption, parse_mode="MarkdownV2")
                except Exception:
                    await update.message.reply_text(caption, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error("cmd_check error: %s", e)
        await update.message.reply_text(f"⚠️ Error: {e}")
        await _notify_admin_error(context.application, e)


def main():
    scheduler = AsyncIOScheduler()

    async def on_startup(application):
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

        subscribers = load_subscribers()
        if subscribers:
            logger.info("Subscribers (%d):", len(subscribers))
            for chat_id in subscribers:
                try:
                    chat = await application.bot.get_chat(chat_id)
                    display = chat.title or chat.full_name or str(chat_id)
                    if chat.username:
                        display = f"{display} (@{chat.username})"
                    logger.info("  • %s (id=%s)", display, chat_id)
                    save_subscriber_name(chat_id, display)
                except Exception as e:
                    logger.info("  • [unknown] (id=%s) — %s", chat_id, e)
        else:
            logger.info(
                "No subscribers yet — will fall back to ADMIN_TELEGRAM_CHAT_ID=%s",
                ADMIN_TELEGRAM_CHAT_ID,
            )

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
