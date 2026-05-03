from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.infrastructure.db.models.user import User


class UserRepository:
    def get_by_id(self, session: Session, user_id: int) -> Optional[User]:
        return session.query(User).filter(User.id == user_id).one_or_none()

    def get_by_telegram_user_id(self, session: Session, telegram_user_id: int) -> Optional[User]:
        return session.query(User).filter(User.telegram_user_id == telegram_user_id).one_or_none()

    def create_or_update_from_telegram(
        self,
        session: Session,
        telegram_user_id: int,
        telegram_username: Optional[str],
        telegram_display_name: Optional[str],
    ) -> User:
        user = self.get_by_telegram_user_id(session, telegram_user_id)
        now = datetime.utcnow()

        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                telegram_display_name=telegram_display_name,
                name=telegram_display_name,
                is_blocked=False,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
            session.add(user)
            session.flush()
            return user

        user.telegram_username = telegram_username
        user.telegram_display_name = telegram_display_name
        if not user.name:
            user.name = telegram_display_name
        user.last_activity_at = now
        user.updated_at = now
        session.flush()
        return user
