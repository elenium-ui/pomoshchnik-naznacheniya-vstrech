from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.domain.enums.user_role import UserRole
from app.modules.users.service import UserService
from app.bot.keyboards.main import BTN_OPEN_MINIAPP, admin_main_keyboard, user_main_keyboard
from app.bot.keyboards.miniapp import miniapp_open_inline_keyboard

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "Добро пожаловать! Через этого бота вы можете записаться на встречу к Елене Разумовой.\n"
    "Выберите действие в меню ниже: новая заявка, мои заявки и управление текущими записями."
)
WELCOME_MINIAPP_HINT = (
    "Для быстрого сценария используйте кнопку «📱 Открыть Mini App» в меню.\n"
    "Если Mini App временно недоступен, все действия остаются доступны через этого бота."
)
MINIAPP_FALLBACK_TEXT = (
    "Mini App сейчас недоступен. Продолжайте через бот: «📝 Новая заявка» и «📂 Мои заявки»."
)


def build_start_router(settings: Settings, session_factory: sessionmaker) -> Router:
    router = Router(name="start")
    user_service = UserService(session_factory=session_factory)

    @router.message(CommandStart())
    @router.message(F.text.lower().in_({"старт", "start"}))
    async def handle_start(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            logger.warning("/start without from_user")
            return
        await state.clear()

        telegram_user = message.from_user
        role = user_service.resolve_role(telegram_user.id, settings.ADMIN_USER_ID)

        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )

        logger.info(
            "Handled /start: telegram_user_id=%s role=%s user_id=%s",
            telegram_user.id,
            role.value,
            user.id,
        )
        logger.info("Start message sent: telegram_user_id=%s role=%s", telegram_user.id, role.value)

        if settings.MINIAPP_PUBLIC_URL:
            logger.info(
                "Mini App button available: telegram_user_id=%s miniapp_url=%s",
                telegram_user.id,
                settings.MINIAPP_PUBLIC_URL,
            )
        else:
            logger.warning(
                "Mini App URL is not configured. Using bot-only fallback in /start: telegram_user_id=%s",
                telegram_user.id,
            )

        if role == UserRole.ADMIN:
            await message.answer(
                f"{WELCOME_TEXT}\n\n{WELCOME_MINIAPP_HINT}",
                reply_markup=admin_main_keyboard(),
            )
            return

        await message.answer(
            f"{WELCOME_TEXT}\n\n{WELCOME_MINIAPP_HINT}",
            reply_markup=user_main_keyboard(),
        )

    @router.message(F.text == BTN_OPEN_MINIAPP)
    async def handle_open_miniapp(message: Message) -> None:
        if not message.from_user:
            logger.warning("Mini App open requested without from_user")
            return

        telegram_user_id = message.from_user.id
        if not settings.MINIAPP_PUBLIC_URL:
            logger.warning("Mini App fallback used: telegram_user_id=%s reason=url_not_configured", telegram_user_id)
            await message.answer(MINIAPP_FALLBACK_TEXT)
            return

        logger.info(
            "Mini App open button clicked: telegram_user_id=%s miniapp_url=%s",
            telegram_user_id,
            settings.MINIAPP_PUBLIC_URL,
        )
        await message.answer(
            "Откройте Mini App по кнопке ниже.",
            reply_markup=miniapp_open_inline_keyboard(settings.MINIAPP_PUBLIC_URL),
        )

    @router.message(Command("admin"))
    async def handle_admin(message: Message) -> None:
        if not message.from_user:
            logger.warning("/admin without from_user")
            return

        role = user_service.resolve_role(message.from_user.id, settings.ADMIN_USER_ID)
        logger.info("Handled /admin: telegram_user_id=%s role=%s", message.from_user.id, role.value)

        if role != UserRole.ADMIN:
            logger.warning("Unauthorized admin menu access attempt: telegram_user_id=%s", message.from_user.id)
            await message.answer("Эта команда доступна только администратору.")
            return

        await message.answer("Админ-меню доступно.", reply_markup=admin_main_keyboard())

    return router
