from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.application.services.availability import AvailabilityService
from app.config import load_settings
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.admin.service import AdminService
from app.modules.bookings.service import BookingService
from app.modules.users.service import UserService


class MiniAppDataSettings(BaseSettings):
    DATABASE_URL: str = Field(min_length=1)
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@dataclass(frozen=True)
class MiniAppCoreServices:
    user_service: UserService
    booking_service: BookingService
    availability_service: AvailabilityService


@lru_cache(maxsize=1)
def get_core_services() -> MiniAppCoreServices:
    data_settings = MiniAppDataSettings()
    app_settings = load_settings()
    engine = build_engine(database_url=data_settings.DATABASE_URL, log_level=data_settings.LOG_LEVEL)
    session_factory = build_session_factory(engine)
    return MiniAppCoreServices(
        user_service=UserService(session_factory=session_factory),
        booking_service=BookingService(session_factory=session_factory, settings=app_settings),
        availability_service=AvailabilityService(session_factory=session_factory),
    )


@lru_cache(maxsize=1)
def get_admin_service() -> AdminService:
    data_settings = MiniAppDataSettings()
    app_settings = load_settings()
    engine = build_engine(database_url=data_settings.DATABASE_URL, log_level=data_settings.LOG_LEVEL)
    session_factory = build_session_factory(engine)
    return AdminService(
        session_factory=session_factory,
        google_service_account_file=app_settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        google_calendar_id=app_settings.GOOGLE_CALENDAR_ID,
    )
