from __future__ import annotations

import logging

import uvicorn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


class MiniAppApiSettings(BaseSettings):
    MINIAPP_API_HOST: str = "0.0.0.0"
    MINIAPP_API_PORT: int = 8090
    MINIAPP_API_LOG_LEVEL: str = "INFO"
    MINIAPP_API_RELOAD: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def run_api() -> None:
    settings = MiniAppApiSettings()
    setup_logging(settings.MINIAPP_API_LOG_LEVEL)
    logger.info(
        "Starting Mini App API runtime on %s:%s",
        settings.MINIAPP_API_HOST,
        settings.MINIAPP_API_PORT,
    )
    uvicorn.run(
        "app.web.api.app:app",
        host=settings.MINIAPP_API_HOST,
        port=settings.MINIAPP_API_PORT,
        reload=settings.MINIAPP_API_RELOAD,
        log_level=settings.MINIAPP_API_LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    run_api()

