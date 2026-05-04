from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.application.services.availability import AvailabilityService
from app.infrastructure.db.session import build_engine, build_session_factory
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
    settings = MiniAppDataSettings()
    engine = build_engine(database_url=settings.DATABASE_URL, log_level=settings.LOG_LEVEL)
    session_factory = build_session_factory(engine)
    return MiniAppCoreServices(
        user_service=UserService(session_factory=session_factory),
        booking_service=BookingService(session_factory=session_factory),
        availability_service=AvailabilityService(session_factory=session_factory),
    )

