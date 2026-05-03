from pathlib import Path

from app.config import Settings, validate_and_log_settings


def test_settings_validation_success_with_required_values(tmp_path):
    service_account_file = tmp_path / "sa.json"
    service_account_file.write_text("{}", encoding="utf-8")

    settings = Settings(
        BOT_TOKEN="test_token",
        ADMIN_USER_ID=123456,
        TIMEZONE="Europe/Moscow",
        GOOGLE_CALENDAR_ID="calendar@example.com",
        GOOGLE_SERVICE_ACCOUNT_FILE=str(service_account_file),
        DATABASE_URL="sqlite:///./data/test.db",
        LOG_LEVEL="INFO",
    )

    validate_and_log_settings(settings)


def test_settings_validation_fails_for_wrong_timezone(tmp_path):
    service_account_file = tmp_path / "sa.json"
    service_account_file.write_text("{}", encoding="utf-8")

    settings = Settings(
        BOT_TOKEN="test_token",
        ADMIN_USER_ID=123456,
        TIMEZONE="UTC",
        GOOGLE_CALENDAR_ID="calendar@example.com",
        GOOGLE_SERVICE_ACCOUNT_FILE=str(service_account_file),
        DATABASE_URL="sqlite:///./data/test.db",
        LOG_LEVEL="INFO",
    )

    try:
        validate_and_log_settings(settings)
        assert False, "Expected RuntimeError"
    except RuntimeError:
        assert True


def test_settings_validation_fails_if_service_account_file_missing(tmp_path):
    missing_file = tmp_path / "missing.json"

    settings = Settings(
        BOT_TOKEN="test_token",
        ADMIN_USER_ID=123456,
        TIMEZONE="Europe/Moscow",
        GOOGLE_CALENDAR_ID="calendar@example.com",
        GOOGLE_SERVICE_ACCOUNT_FILE=str(missing_file),
        DATABASE_URL="sqlite:///./data/test.db",
        LOG_LEVEL="INFO",
    )

    try:
        validate_and_log_settings(settings)
        assert False, "Expected RuntimeError"
    except RuntimeError:
        assert True
