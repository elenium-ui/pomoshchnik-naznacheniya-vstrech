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
from app.bot.keyboards.main import admin_main_keyboard, user_main_keyboard

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "Добро пожаловать! Через этого бота вы можете записаться на встречу к Елене Разумовой.\n"
    "Выберите действие в меню ниже: новая заявка, мои заявки и управление текущими записями."
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

        if role == UserRole.ADMIN:
            await message.answer(
                WELCOME_TEXT,
                reply_markup=admin_main_keyboard(),
            )
            return

        await message.answer(
            WELCOME_TEXT,
            reply_markup=user_main_keyboard(),
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
