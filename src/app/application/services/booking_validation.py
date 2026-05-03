from __future__ import annotations

import re
from typing import Optional

from app.domain.enums.booking import DURATION_OPTIONS, MeetingFormat

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+0-9()\-\s]{6,20}$")


def normalize_text(value: str) -> str:
    return value.strip()


def validate_name(value: str) -> str:
    name = normalize_text(value)
    if len(name) < 2:
        raise ValueError("Имя должно быть не короче 2 символов.")
    if len(name) > 100:
        raise ValueError("Имя должно быть не длиннее 100 символов.")
    return name


def validate_topic(value: str) -> str:
    topic = normalize_text(value)
    if len(topic) < 3:
        raise ValueError("Тема должна быть не короче 3 символов.")
    if len(topic) > 255:
        raise ValueError("Тема должна быть не длиннее 255 символов.")
    return topic


def validate_meeting_format(value: str) -> str:
    norm = normalize_text(value).lower()
    if norm not in {MeetingFormat.ONLINE.value, MeetingFormat.OFFLINE.value}:
        raise ValueError("Формат должен быть 'онлайн' или 'офлайн'.")
    return norm


def validate_duration(value: str) -> int:
    raw = normalize_text(value).replace("минут", "").replace("мин", "").strip()
    if not raw.isdigit():
        raise ValueError("Длительность должна быть числом из списка: 15/30/45/60/90.")
    duration = int(raw)
    if duration not in DURATION_OPTIONS:
        raise ValueError("Длительность должна быть из списка: 15/30/45/60/90.")
    return duration


def parse_optional_email(value: str) -> Optional[str]:
    email = normalize_text(value)
    if not email:
        return None
    if not _EMAIL_RE.match(email):
        raise ValueError("Похоже, email введен в неверном формате.")
    return email


def parse_optional_comment(value: str) -> Optional[str]:
    comment = normalize_text(value)
    return comment or None


def validate_phone(value: str) -> str:
    phone = normalize_text(value)
    if not _PHONE_RE.match(phone):
        raise ValueError("Введите телефон в формате +79991234567 или похожем.")
    return phone


def requires_alternative_contact(has_username: bool, email: Optional[str]) -> bool:
    return (not has_username) and (not email)
