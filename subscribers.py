import json
import logging
import os

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("DATA_DIR", ".")
SUBSCRIBERS_FILE = os.path.join(_DATA_DIR, "subscribers.json")


def load_subscribers() -> list[int]:
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            return json.load(f)
    return []


def save_subscribers(chat_ids: list[int]) -> None:
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(chat_ids, f, indent=2)


def add_subscriber(chat_id: int) -> bool:
    """Add chat_id if not already present. Returns True if newly added."""
    subscribers = load_subscribers()
    if chat_id in subscribers:
        return False
    subscribers.append(chat_id)
    save_subscribers(subscribers)
    logger.info("New subscriber added: chat_id=%s (total: %d)", chat_id, len(subscribers))
    return True
