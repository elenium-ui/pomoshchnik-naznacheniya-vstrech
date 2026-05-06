from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl

from app.application.services.roles import resolve_user_role
from app.domain.enums.user_role import UserRole

logger = logging.getLogger(__name__)
ModeName = Literal["client", "admin"]


class TelegramInitDataError(ValueError):
    """Raised when Telegram initData cannot be trusted."""


class AccessDeniedError(PermissionError):
    """Raised when requested mode is forbidden for current user."""


@dataclass(frozen=True)
class TelegramWebAppUser:
    telegram_user_id: int
    first_name: str | None
    last_name: str | None
    username: str | None

    @property
    def role_mode(self) -> str:
        return "client"


@dataclass(frozen=True)
class MiniAppSession:
    user: TelegramWebAppUser
    is_admin: bool
    available_modes: tuple[ModeName, ...]
    default_mode: ModeName


class MiniAppAuthService:
    def __init__(
        self,
        bot_token: str,
        admin_user_id: int,
        max_auth_age_seconds: int = 86_400,
    ) -> None:
        self._bot_token = bot_token
        self._admin_user_id = admin_user_id
        self._max_auth_age_seconds = max_auth_age_seconds

    def build_session(self, init_data: str) -> MiniAppSession:
        raw_fields = self._parse_init_data(init_data)
        self._verify_signature(raw_fields)
        self._verify_freshness(raw_fields)

        tg_user = self._extract_user(raw_fields)
        role = resolve_user_role(
            telegram_user_id=tg_user.telegram_user_id,
            admin_user_id=self._admin_user_id,
        )
        is_admin = role == UserRole.ADMIN
        available_modes: tuple[str, ...] = ("client", "admin") if is_admin else ("client",)
        default_mode = "client"

        logger.info(
            "Mini App auth success: telegram_user_id=%s is_admin=%s",
            tg_user.telegram_user_id,
            is_admin,
        )
        return MiniAppSession(
            user=tg_user,
            is_admin=is_admin,
            available_modes=available_modes,
            default_mode=default_mode,
        )

    def validate_mode_access(self, session: MiniAppSession, mode: ModeName) -> ModeName:
        if mode not in session.available_modes:
            logger.warning(
                "Mini App access denied: telegram_user_id=%s requested_mode=%s available_modes=%s",
                session.user.telegram_user_id,
                mode,
                ",".join(session.available_modes),
            )
            raise AccessDeniedError("Requested mode is not available for this user.")

        logger.info(
            "Mini App mode accepted: telegram_user_id=%s mode=%s",
            session.user.telegram_user_id,
            mode,
        )
        return mode

    def _parse_init_data(self, init_data: str) -> dict[str, str]:
        pairs = parse_qsl(init_data, keep_blank_values=True)
        if not pairs:
            logger.warning("Mini App auth failed: empty initData payload.")
            raise TelegramInitDataError("Empty initData payload.")
        parsed = dict(pairs)
        if "hash" not in parsed:
            logger.warning("Mini App auth failed: initData hash field missing.")
            raise TelegramInitDataError("initData hash field is missing.")
        return parsed

    def _verify_signature(self, fields: dict[str, str]) -> None:
        provided_hash = fields.get("hash", "")
        check_lines = [f"{k}={v}" for k, v in sorted(fields.items()) if k != "hash"]
        data_check_string = "\n".join(check_lines)

        secret_key = hmac.new(
            key=b"WebAppData",
            msg=self._bot_token.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, provided_hash):
            logger.warning("Mini App auth failed: invalid initData signature.")
            raise TelegramInitDataError("Invalid initData signature.")

    def _verify_freshness(self, fields: dict[str, str]) -> None:
        raw_auth_date = fields.get("auth_date")
        if raw_auth_date is None:
            logger.warning("Mini App auth failed: auth_date field missing.")
            raise TelegramInitDataError("auth_date field is missing.")

        try:
            auth_date = int(raw_auth_date)
        except ValueError as exc:
            logger.warning("Mini App auth failed: auth_date has invalid format.")
            raise TelegramInitDataError("auth_date format is invalid.") from exc

        age_seconds = int(time.time()) - auth_date
        if age_seconds > self._max_auth_age_seconds:
            logger.warning(
                "Mini App auth failed: auth payload expired (age=%s sec, max=%s sec).",
                age_seconds,
                self._max_auth_age_seconds,
            )
            raise TelegramInitDataError("initData is expired.")

    def _extract_user(self, fields: dict[str, str]) -> TelegramWebAppUser:
        raw_user = fields.get("user")
        if raw_user is None:
            logger.warning("Mini App auth failed: user field missing.")
            raise TelegramInitDataError("user field is missing.")

        try:
            user_payload: dict[str, Any] = json.loads(raw_user)
        except json.JSONDecodeError as exc:
            logger.warning("Mini App auth failed: user field is not valid JSON.")
            raise TelegramInitDataError("user payload is invalid JSON.") from exc

        user_id = user_payload.get("id")
        if not isinstance(user_id, int):
            logger.warning("Mini App auth failed: user.id missing or invalid.")
            raise TelegramInitDataError("user.id is missing or invalid.")

        return TelegramWebAppUser(
            telegram_user_id=user_id,
            first_name=user_payload.get("first_name"),
            last_name=user_payload.get("last_name"),
            username=user_payload.get("username"),
        )
