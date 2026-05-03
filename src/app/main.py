import argparse
import asyncio
import logging

from aiogram import Bot

from app.bot.runtime import run_polling_bot
from app.config import load_settings
from app.infrastructure.db.session import build_engine, build_session_factory, check_database_connection
from app.logging_config import setup_logging
from app.modules.jobs.runner import run_jobs_once_with_notifications
from app.modules.jobs.service import JobsService

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 2 bootstrap for 'Запись на встречу'"
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate environment configuration and exit.",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run startup health-check (config + DB connection).",
    )
    parser.add_argument(
        "--run-bot",
        action="store_true",
        help="Run Telegram bot in long polling mode.",
    )
    parser.add_argument(
        "--run-jobs-once",
        action="store_true",
        help="Run background maintenance jobs once (TTL + cleanup).",
    )
    args = parser.parse_args()

    setup_logging(level="INFO")
    settings = load_settings()
    setup_logging(level=settings.LOG_LEVEL)

    if args.check_config:
        logger.info("Configuration check completed successfully.")
        return

    if args.health_check:
        engine = build_engine(settings.DATABASE_URL, settings.LOG_LEVEL)
        check_database_connection(engine)
        logger.info("Health-check completed successfully.")
        return

    if args.run_bot:
        asyncio.run(run_polling_bot(settings))
        return

    if args.run_jobs_once:
        engine = build_engine(settings.DATABASE_URL, settings.LOG_LEVEL)
        check_database_connection(engine)
        session_factory = build_session_factory(engine)
        jobs_service = JobsService(session_factory=session_factory)
        bot = Bot(token=settings.BOT_TOKEN)

        async def _run_once() -> None:
            try:
                result = await run_jobs_once_with_notifications(
                    jobs_service=jobs_service,
                    notify_user=lambda tg_id, text: bot.send_message(chat_id=tg_id, text=text),
                )
                logger.info(
                    "Jobs once completed: expired_processed=%s status_history_deleted=%s",
                    result.expired_processed,
                    result.status_history_deleted,
                )
            finally:
                await bot.session.close()
                engine.dispose()

        asyncio.run(_run_once())
        return

    logger.info("No action selected. Use --run-bot, --check-config, --health-check or --run-jobs-once.")


if __name__ == "__main__":
    main()
