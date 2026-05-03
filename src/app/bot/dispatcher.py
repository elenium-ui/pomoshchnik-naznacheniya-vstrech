from aiogram import Dispatcher
from sqlalchemy.orm import sessionmaker

from app.bot.handlers.bookings import build_booking_router
from app.bot.handlers.start import build_start_router
from app.config import Settings


def build_dispatcher(settings: Settings, session_factory: sessionmaker) -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(build_start_router(settings=settings, session_factory=session_factory))
    dp.include_router(build_booking_router(settings=settings, session_factory=session_factory))
    return dp
