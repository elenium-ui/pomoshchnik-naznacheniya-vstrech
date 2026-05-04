from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.web.services.auth import MiniAppAuthService


class MiniAppAuthSettings(BaseSettings):
    BOT_TOKEN: str = Field(min_length=1)
    ADMIN_USER_ID: int
    MINIAPP_AUTH_MAX_AGE_SECONDS: int = 86_400

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_auth_service() -> MiniAppAuthService:
    settings = MiniAppAuthSettings()
    return MiniAppAuthService(
        bot_token=settings.BOT_TOKEN,
        admin_user_id=settings.ADMIN_USER_ID,
        max_auth_age_seconds=settings.MINIAPP_AUTH_MAX_AGE_SECONDS,
    )

