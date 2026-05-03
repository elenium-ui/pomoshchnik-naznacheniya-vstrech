from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.user import User
from app.infrastructure.db.repositories.booking_repository import BookingRepository
from app.infrastructure.db.repositories.status_history_repository import StatusHistoryRepository

logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class ExpiredBookingNotice:
    booking_id: int
    user_telegram_user_id: int
    text: str


@dataclass(frozen=True)
class JobsRunResult:
    expired_processed: int
    status_history_deleted: int
    notices: list[ExpiredBookingNotice]


class JobsService:
    def __init__(
        self,
        session_factory: sessionmaker,
        booking_repository: BookingRepository | None = None,
        status_history_repository: StatusHistoryRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._booking_repository = booking_repository or BookingRepository()
        self._status_history_repository = status_history_repository or StatusHistoryRepository()

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

    def run_once(self, now_msk_naive: datetime | None = None) -> JobsRunResult:
        now_value = now_msk_naive or datetime.now(MSK).replace(tzinfo=None)
        logger.info("Background jobs run started: now=%s", now_value.isoformat())

        expired_count, notices = self._expire_outdated_bookings(now_value)
        deleted_history = self._cleanup_old_status_history(now_value)

        logger.info(
            "Background jobs run finished: expired_processed=%s status_history_deleted=%s",
            expired_count,
            deleted_history,
        )
        return JobsRunResult(
            expired_processed=expired_count,
            status_history_deleted=deleted_history,
            notices=notices,
        )

    def _expire_outdated_bookings(self, now_msk_naive: datetime) -> tuple[int, list[ExpiredBookingNotice]]:
        with self._session_scope() as session:
            expired_bookings = self._booking_repository.list_expired_pending_decision(
                session=session,
                now_msk_naive=now_msk_naive,
                limit=200,
            )
            logger.info("TTL scan: found_expired=%s", len(expired_bookings))
            notices: list[ExpiredBookingNotice] = []
            for booking in expired_bookings:
                user = session.query(User).filter(User.id == booking.user_id).one_or_none()
                if user is None:
                    logger.warning("TTL auto-cancel skipped user lookup: booking_id=%s", booking.id)
                    continue

                old_status = booking.status
                booking.previous_slot_start_at = booking.previous_slot_start_at or booking.slot_start_at
                booking.previous_slot_end_at = booking.previous_slot_end_at or booking.slot_end_at
                booking.slot_start_at = None
                booking.slot_end_at = None
                booking.requested_new_slot_start_at = None
                booking.requested_new_slot_end_at = None
                booking.expires_at = None
                booking.status = "expired"
                booking.updated_at = datetime.utcnow()
                self._status_history_repository.create_entry(
                    session=session,
                    booking_id=booking.id,
                    old_status=old_status,
                    new_status="expired",
                    changed_by="system:ttl",
                )
                logger.info("TTL auto-cancel booking: booking_id=%s", booking.id)
                notices.append(
                    ExpiredBookingNotice(
                        booking_id=booking.id,
                        user_telegram_user_id=user.telegram_user_id,
                        text=(
                            "Заявка автоматически отменена по TTL (72 часа без решения).\n"
                            f"Заявка #{booking.id}\n"
                            "Вы можете создать новую заявку."
                        ),
                    )
                )
            return len(expired_bookings), notices

    def _cleanup_old_status_history(self, now_msk_naive: datetime) -> int:
        before_dt = now_msk_naive - timedelta(days=30)
        with self._session_scope() as session:
            deleted = self._status_history_repository.delete_older_than(session=session, before_dt=before_dt)
            logger.info("Status history cleanup: before=%s deleted=%s", before_dt.isoformat(), deleted)
            return int(deleted)
