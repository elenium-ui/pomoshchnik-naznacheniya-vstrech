from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

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


async def _configure_telegram_ui(bot: Bot, settings: Settings) -> None:
    """Configure Telegram menu with a direct Mini App entry point."""
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Открыть главное меню"),
                BotCommand(command="admin", description="Открыть меню администратора"),
            ]
        )
        if settings.MINIAPP_PUBLIC_URL:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Открыть Mini App", web_app=WebAppInfo(url=settings.MINIAPP_PUBLIC_URL))
            )
            logger.info("Telegram menu button configured as Mini App launcher.")
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("Telegram command menu configured.")
    except Exception:
        logger.exception("Failed to configure Telegram command menu.")


async def run_polling_bot(settings: Settings) -> None:
    engine = build_engine(settings.DATABASE_URL, settings.LOG_LEVEL)
    check_database_connection(engine)
    session_factory = build_session_factory(engine)

    bot = Bot(token=settings.BOT_TOKEN)
    await _configure_telegram_ui(bot, settings)
    dp = build_dispatcher(settings=settings, session_factory=session_factory)
    jobs_task: asyncio.Task | None = None
    if settings.BOT_BACKGROUND_JOBS_ENABLED:
        jobs_service = JobsService(session_factory=session_factory)
        jobs_task = asyncio.create_task(_background_jobs_loop(jobs_service=jobs_service, bot=bot, interval_seconds=60))
    else:
        logger.info("Background scheduler is disabled in bot runtime by BOT_BACKGROUND_JOBS_ENABLED=false")

    logger.info("Starting Telegram bot in long polling mode.")
    try:
        await bot.delete_webhook(
            drop_pending_updates=settings.TELEGRAM_DROP_PENDING_UPDATES_ON_START
        )
        await dp.start_polling(bot)
    finally:
        if jobs_task is not None:
            jobs_task.cancel()
            try:
                await jobs_task
            except asyncio.CancelledError:
                logger.info("Background scheduler stopped.")
        await bot.session.close()
        engine.dispose()
        logger.info("Bot stopped.")


def _build_webhook_url(settings: Settings) -> str:
    base = (settings.TELEGRAM_WEBHOOK_BASE_URL or "").rstrip("/")
    path = settings.TELEGRAM_WEBHOOK_PATH
    return f"{base}{path}"


async def _health_handler(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def run_webhook_bot(settings: Settings) -> None:
    engine = build_engine(settings.DATABASE_URL, settings.LOG_LEVEL)
    check_database_connection(engine)
    session_factory = build_session_factory(engine)

    bot = Bot(token=settings.BOT_TOKEN)
    await _configure_telegram_ui(bot, settings)
    dp = build_dispatcher(settings=settings, session_factory=session_factory)
    jobs_task: asyncio.Task | None = None
    if settings.BOT_BACKGROUND_JOBS_ENABLED:
        jobs_service = JobsService(session_factory=session_factory)
        jobs_task = asyncio.create_task(
            _background_jobs_loop(jobs_service=jobs_service, bot=bot, interval_seconds=60)
        )
    else:
        logger.info("Background scheduler is disabled in bot runtime by BOT_BACKGROUND_JOBS_ENABLED=false")

    app = web.Application()
    app.router.add_get("/health", _health_handler)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
    )
    webhook_handler.register(app, path=settings.TELEGRAM_WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    webhook_url = _build_webhook_url(settings)
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
        drop_pending_updates=settings.TELEGRAM_DROP_PENDING_UPDATES_ON_START,
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=settings.TELEGRAM_WEBHOOK_LISTEN_HOST,
        port=settings.TELEGRAM_WEBHOOK_LISTEN_PORT,
    )
    await site.start()

    logger.info(
        "Starting Telegram bot in webhook mode: listen=%s:%s webhook_url=%s",
        settings.TELEGRAM_WEBHOOK_LISTEN_HOST,
        settings.TELEGRAM_WEBHOOK_LISTEN_PORT,
        webhook_url,
    )

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        if jobs_task is not None:
            jobs_task.cancel()
            try:
                await jobs_task
            except asyncio.CancelledError:
                logger.info("Background scheduler stopped.")
        await runner.cleanup()
        await bot.session.close()
        engine.dispose()
        logger.info("Bot stopped.")


async def run_bot(settings: Settings) -> None:
    mode = settings.TELEGRAM_DELIVERY_MODE.strip().lower()
    if mode == "webhook":
        await run_webhook_bot(settings)
        return
    await run_polling_bot(settings)
