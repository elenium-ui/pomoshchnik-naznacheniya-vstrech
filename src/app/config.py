import logging
from pathlib import Path
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

    if errors:
        for error in errors:
            logger.error("Configuration validation error: %s", error)
        raise RuntimeError("Configuration validation failed.")

    logger.info(
        "Configuration loaded: BOT_TOKEN=%s ADMIN_USER_ID=%s TIMEZONE=%s GOOGLE_CALENDAR_ID=%s DATABASE_URL=%s",
        _mask(settings.BOT_TOKEN),
        settings.ADMIN_USER_ID,
        settings.TIMEZONE,
        _mask(settings.GOOGLE_CALENDAR_ID),
        settings.DATABASE_URL,
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
