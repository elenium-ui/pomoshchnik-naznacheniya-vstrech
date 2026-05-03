from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy.orm import Session, sessionmaker

from app.application.services.roles import resolve_user_role
from app.domain.enums.user_role import UserRole
from app.infrastructure.db.models.user import User
from app.infrastructure.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session_factory: sessionmaker, repository: Optional[UserRepository] = None) -> None:
        self._session_factory = session_factory
        self._repository = repository or UserRepository()

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def resolve_role(self, telegram_user_id: int, admin_user_id: int) -> UserRole:
        return resolve_user_role(telegram_user_id, admin_user_id)

    def ensure_user_from_telegram(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str],
        telegram_display_name: Optional[str],
    ) -> User:
        with self._session_scope() as session:
            user = self._repository.create_or_update_from_telegram(
                session=session,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                telegram_display_name=telegram_display_name,
            )
            logger.info("User synced from Telegram: telegram_user_id=%s user_id=%s", telegram_user_id, user.id)
            return user

    def update_user_profile(
        self,
        telegram_user_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        with self._session_scope() as session:
            user = self._repository.get_by_telegram_user_id(session, telegram_user_id)
            if user is None:
                raise ValueError("Пользователь не найден.")

            if name is not None:
                user.name = name
            if phone is not None:
                user.phone = phone
            if email is not None:
                user.email = email

            session.flush()
            logger.info(
                "User profile updated: telegram_user_id=%s name=%s phone=%s email=%s",
                telegram_user_id,
                bool(name),
                bool(phone),
                bool(email),
            )
            return user

    def get_user_by_id(self, user_id: int) -> User:
        with self._session_scope() as session:
            user = self._repository.get_by_id(session, user_id=user_id)
            if user is None:
                raise ValueError("Пользователь не найден.")
            return user

    def is_blocked(self, telegram_user_id: int) -> bool:
        with self._session_scope() as session:
            user = self._repository.get_by_telegram_user_id(session, telegram_user_id=telegram_user_id)
            return bool(user and user.is_blocked)
