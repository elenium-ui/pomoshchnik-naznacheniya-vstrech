from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.bot.dispatcher import build_dispatcher
from app.config import Settings
from app.infrastructure.db.session import build_engine, build_session_factory, check_database_connection
from app.modules.jobs.runner import run_jobs_once_with_notifications
from app.modules.jobs.service import JobsService

logger = logging.getLogger(__name__)


async def _background_jobs_loop(
    jobs_service: JobsService,
    bot: Bot,
    interval_seconds: int = 60,
) -> None:
    logger.info("Background scheduler started: interval_seconds=%s", interval_seconds)
    while True:
        try:
            await run_jobs_once_with_notifications(
                jobs_service=jobs_service,
                notify_user=lambda tg_id, text: bot.send_message(chat_id=tg_id, text=text),
            )
        except Exception:
            logger.exception("Background scheduler iteration failed.")
        await asyncio.sleep(interval_seconds)


async def run_polling_bot(settings: Settings) -> None:
    engine = build_engine(settings.DATABASE_URL, settings.LOG_LEVEL)
    check_database_connection(engine)
    session_factory = build_session_factory(engine)

    bot = Bot(token=settings.BOT_TOKEN)
    dp = build_dispatcher(settings=settings, session_factory=session_factory)
    jobs_service = JobsService(session_factory=session_factory)
    jobs_task = asyncio.create_task(_background_jobs_loop(jobs_service=jobs_service, bot=bot, interval_seconds=60))

    logger.info("Starting Telegram bot in long polling mode.")
    try:
        await dp.start_polling(bot)
    finally:
        jobs_task.cancel()
        try:
            await jobs_task
        except asyncio.CancelledError:
            logger.info("Background scheduler stopped.")
        await bot.session.close()
        engine.dispose()
        logger.info("Bot stopped.")
