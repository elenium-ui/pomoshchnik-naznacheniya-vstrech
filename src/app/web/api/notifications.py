from __future__ import annotations

import json
import logging
from urllib import error, parse, request

from app.config import load_settings

logger = logging.getLogger(__name__)


def send_telegram_text(chat_id: int, text: str) -> None:
    settings = load_settings()
    token = settings.BOT_TOKEN
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = parse.urlencode({"chat_id": str(chat_id), "text": text}).encode("utf-8")
    req = request.Request(endpoint, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with request.urlopen(req, timeout=7) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        if not parsed.get("ok", False):
            logger.warning("Telegram notification API returned non-ok response: %s", parsed)
    except error.URLError:
        logger.exception("Telegram notification delivery failed: chat_id=%s", chat_id)
