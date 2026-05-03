import logging
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    BOT_TOKEN: str = Field(min_length=1)
    ADMIN_USER_ID: int
    TIMEZONE: str = "Europe/Moscow"
    GOOGLE_CALENDAR_ID: str = Field(min_length=1)
    GOOGLE_SERVICE_ACCOUNT_FILE: str = Field(min_length=1)
    DATABASE_URL: str = Field(min_length=1)
    LOG_LEVEL: str = "INFO"
    TELEGRAM_DELIVERY_MODE: str = "polling"
    TELEGRAM_WEBHOOK_BASE_URL: Optional[str] = None
    TELEGRAM_WEBHOOK_PATH: str = "/telegram/webhook"
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None
    TELEGRAM_WEBHOOK_LISTEN_HOST: str = "0.0.0.0"
    TELEGRAM_WEBHOOK_LISTEN_PORT: int = 8080
    TELEGRAM_DROP_PENDING_UPDATES_ON_START: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-3:]}"


def validate_and_log_settings(settings: Settings) -> None:
    """Validate critical settings and log only safe diagnostics."""
    errors: list[str] = []

    if settings.TIMEZONE != "Europe/Moscow":
        errors.append("TIMEZONE must be Europe/Moscow for MVP stage.")

    service_account_path = Path(settings.GOOGLE_SERVICE_ACCOUNT_FILE)
    if not service_account_path.exists():
        errors.append(
            "GOOGLE_SERVICE_ACCOUNT_FILE does not exist. "
            f"Expected path: {service_account_path}"
        )

    if not settings.DATABASE_URL.startswith("sqlite://"):
        errors.append("DATABASE_URL should point to SQLite at this stage.")

    mode = settings.TELEGRAM_DELIVERY_MODE.strip().lower()
    if mode not in {"polling", "webhook"}:
        errors.append("TELEGRAM_DELIVERY_MODE must be either 'polling' or 'webhook'.")

    if mode == "webhook":
        if not settings.TELEGRAM_WEBHOOK_BASE_URL:
            errors.append("TELEGRAM_WEBHOOK_BASE_URL is required for webhook mode.")
        elif not settings.TELEGRAM_WEBHOOK_BASE_URL.startswith("https://"):
            errors.append("TELEGRAM_WEBHOOK_BASE_URL must start with https://")

        if not settings.TELEGRAM_WEBHOOK_PATH.startswith("/"):
            errors.append("TELEGRAM_WEBHOOK_PATH must start with '/'.")

        if not settings.TELEGRAM_WEBHOOK_SECRET:
            errors.append("TELEGRAM_WEBHOOK_SECRET is required for webhook mode.")

        if settings.TELEGRAM_WEBHOOK_LISTEN_PORT <= 0:
            errors.append("TELEGRAM_WEBHOOK_LISTEN_PORT must be a positive integer.")

    if errors:
        for error in errors:
            logger.error("Configuration validation error: %s", error)
        raise RuntimeError("Configuration validation failed.")

    logger.info(
        (
            "Configuration loaded: BOT_TOKEN=%s ADMIN_USER_ID=%s TIMEZONE=%s "
            "GOOGLE_CALENDAR_ID=%s DATABASE_URL=%s TELEGRAM_DELIVERY_MODE=%s "
            "TELEGRAM_WEBHOOK_BASE_URL=%s TELEGRAM_WEBHOOK_PATH=%s"
        ),
        _mask(settings.BOT_TOKEN),
        settings.ADMIN_USER_ID,
        settings.TIMEZONE,
        _mask(settings.GOOGLE_CALENDAR_ID),
        settings.DATABASE_URL,
        settings.TELEGRAM_DELIVERY_MODE,
        settings.TELEGRAM_WEBHOOK_BASE_URL or "<none>",
        settings.TELEGRAM_WEBHOOK_PATH,
    )


def load_settings() -> Settings:
    try:
        settings = Settings()
        validate_and_log_settings(settings)
        logger.info("Required configuration is valid.")
        return settings
    except Exception:
        logger.exception("Failed to load configuration.")
        raise
