import pytest

from app.application.services.booking_validation import (
    parse_optional_email,
    requires_alternative_contact,
    validate_duration,
    validate_meeting_format,
    validate_name,
    validate_phone,
    validate_topic,
)


def test_validate_name_ok():
    assert validate_name("Иван") == "Иван"


def test_validate_name_too_short():
    with pytest.raises(ValueError):
        validate_name("А")


def test_validate_topic_ok():
    assert validate_topic("Обсудить проект") == "Обсудить проект"


def test_validate_meeting_format_ok():
    assert validate_meeting_format("онлайн") == "онлайн"


def test_validate_duration_ok():
    assert validate_duration("30 минут") == 30


def test_parse_optional_email_skip():
    assert parse_optional_email("") is None


def test_parse_optional_email_invalid():
    with pytest.raises(ValueError):
        parse_optional_email("bad_email")


def test_validate_phone_ok():
    assert validate_phone("+79991234567") == "+79991234567"


def test_requires_alternative_contact_without_username_and_email():
    assert requires_alternative_contact(has_username=False, email=None) is True


def test_requires_alternative_contact_with_email():
    assert requires_alternative_contact(has_username=False, email="a@b.com") is False
