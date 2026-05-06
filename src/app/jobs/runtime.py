from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.config import load_settings
from app.infrastructure.db.session import build_engine, build_session_factory, check_database_connection
from app.logging_config import setup_logging
from app.modules.jobs.runner import run_jobs_once_with_notifications
from app.modules.jobs.service import JobsService

logger = logging.getLogger(__name__)


async def run_jobs_daemon(interval_seconds: int = 60) -> None:
    settings = load_settings()
    setup_logging(settings.LOG_LEVEL)

    engine = build_engine(settings.DATABASE_URL, settings.LOG_LEVEL)
    check_database_connection(engine)
    session_factory = build_session_factory(engine)
    jobs_service = JobsService(session_factory=session_factory)
    bot = Bot(token=settings.BOT_TOKEN)

    logger.info("Starting jobs daemon: interval_seconds=%s", interval_seconds)
    try:
        while True:
            try:
                await run_jobs_once_with_notifications(
                    jobs_service=jobs_service,
                    notify_user=lambda tg_id, text: bot.send_message(chat_id=tg_id, text=text),
                )
            except Exception:
                logger.exception("Jobs daemon iteration failed.")
            await asyncio.sleep(interval_seconds)
    finally:
        await bot.session.close()
        engine.dispose()
        logger.info("Jobs daemon stopped.")


if __name__ == "__main__":
    asyncio.run(run_jobs_daemon())
