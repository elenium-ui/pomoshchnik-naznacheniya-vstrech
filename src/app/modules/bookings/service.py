from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.user import User
from app.infrastructure.calendar.google_calendar_client import (
    CalendarClient,
    CalendarEventRequest,
    GoogleCalendarClient,
)
from app.infrastructure.db.repositories.booking_repository import BookingRepository
from app.infrastructure.db.repositories.status_history_repository import StatusHistoryRepository
from app.infrastructure.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class BookingDecisionResult:
    booking: Booking
    user: User


class BookingService:
    def __init__(
        self,
        session_factory: sessionmaker,
        repository: Optional[BookingRepository] = None,
        user_repository: Optional[UserRepository] = None,
        status_history_repository: Optional[StatusHistoryRepository] = None,
        calendar_client: CalendarClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repository = repository or BookingRepository()
        self._user_repository = user_repository or UserRepository()
        self._status_history_repository = status_history_repository or StatusHistoryRepository()
        self._calendar_client = calendar_client
        self._settings = settings

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

    def create_draft(self, user_id: int) -> Booking:
        with self._session_scope() as session:
            booking = self._repository.create_draft(session=session, user_id=user_id)
            logger.info("Draft booking created: booking_id=%s user_id=%s", booking.id, user_id)
            return booking

    def update_booking_fields(self, booking_id: int, user_id: int, **fields) -> Booking:
        with self._session_scope() as session:
            booking = self._repository.get_by_id_for_user(session, booking_id=booking_id, user_id=user_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            self._repository.update_fields(booking, **fields)
            session.flush()
            logger.info("Draft booking updated: booking_id=%s fields=%s", booking.id, list(fields.keys()))
            return booking

    def list_active_bookings(self, user_id: int, now_msk_naive: datetime | None = None) -> list[Booking]:
        effective_now = now_msk_naive or datetime.now(MSK).replace(tzinfo=None)
        with self._session_scope() as session:
            bookings = self._repository.list_active_by_user(
                session=session,
                user_id=user_id,
                now_msk_naive=effective_now,
            )
            logger.info("Active bookings listed: user_id=%s count=%s", user_id, len(bookings))
            return bookings

    def list_history_bookings(self, user_id: int, now_msk_naive: datetime) -> list[Booking]:
        with self._session_scope() as session:
            bookings = self._repository.list_history_completed_by_user(
                session=session,
                user_id=user_id,
                now_msk_naive=now_msk_naive,
            )
            logger.info("History bookings listed: user_id=%s count=%s", user_id, len(bookings))
            return bookings

    def list_pending_decision_bookings(self, limit: int = 20) -> list[Booking]:
        with self._session_scope() as session:
            bookings = self._repository.list_admin_queue(session=session, limit=limit)
            logger.info("Admin queue bookings listed: count=%s", len(bookings))
            return bookings

    def list_confirmed_bookings(self, limit: int = 20) -> list[Booking]:
        with self._session_scope() as session:
            bookings = self._repository.list_confirmed(session=session, limit=limit)
            logger.info("Admin confirmed bookings listed: count=%s", len(bookings))
            return bookings

    def search_bookings_for_admin(
        self,
        *,
        status: str | None = None,
        target_date: date | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[tuple[Booking, User]]:
        with self._session_scope() as session:
            rows = self._repository.search_for_admin(
                session=session,
                status=status,
                target_date=target_date,
                search=search,
                limit=limit,
            )
            logger.info(
                "Admin booking search via booking service: status=%s date=%s search=%s count=%s",
                status,
                target_date.isoformat() if target_date else None,
                bool(search),
                len(rows),
            )
            return rows

    def get_booking_for_admin(self, booking_id: int) -> tuple[Booking, User]:
        with self._session_scope() as session:
            row = self._repository.get_by_id_with_user(session=session, booking_id=booking_id)
            if row is None:
                raise ValueError("Заявка не найдена.")
            return row

    def update_booking_admin_fields(
        self,
        *,
        booking_id: int,
        admin_telegram_user_id: int,
        admin_public_comment: str | None,
        meeting_link: str | None,
    ) -> tuple[Booking, User]:
        with self._session_scope() as session:
            row = self._repository.get_by_id_with_user(session=session, booking_id=booking_id)
            if row is None:
                raise ValueError("Заявка не найдена.")
            booking, user = row
            self._repository.update_fields(
                booking,
                admin_public_comment=admin_public_comment,
                meeting_link=meeting_link,
            )
            session.flush()
            logger.info(
                "Admin booking meta updated: booking_id=%s admin_tg_id=%s comment=%s link=%s",
                booking.id,
                admin_telegram_user_id,
                bool(admin_public_comment),
                bool(meeting_link),
            )
            return booking, user

    def get_booking_for_user(self, booking_id: int, user_id: int) -> Booking:
        with self._session_scope() as session:
            booking = self._repository.get_by_id_for_user(session, booking_id=booking_id, user_id=user_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            return booking

    def count_future_active_for_limit(self, user_id: int, now_msk_naive: datetime) -> int:
        with self._session_scope() as session:
            count = self._repository.count_future_active_for_limit(
                session=session,
                user_id=user_id,
                now_msk_naive=now_msk_naive,
            )
            logger.info("Future active booking count: user_id=%s count=%s", user_id, count)
            return count

    def hold_slot_and_submit(
        self,
        booking_id: int,
        user_id: int,
        slot_start_at_msk_naive: datetime,
        slot_end_at_msk_naive: datetime,
        expires_at_msk_naive: datetime,
    ) -> Booking:
        with self._session_scope() as session:
            booking = self._repository.get_by_id_for_user(session, booking_id=booking_id, user_id=user_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")

            if self._repository.has_slot_conflict(
                session=session,
                slot_start_at=slot_start_at_msk_naive,
                slot_end_at=slot_end_at_msk_naive,
                exclude_booking_id=booking.id,
            ):
                raise ValueError("Слот уже занят. Выберите другой.")

            self._repository.update_fields(
                booking,
                slot_start_at=slot_start_at_msk_naive,
                slot_end_at=slot_end_at_msk_naive,
                expires_at=expires_at_msk_naive,
            )
            self._transition_status(
                session=session,
                booking=booking,
                new_status="pending_decision",
                changed_by="user",
            )
            session.flush()

            logger.info(
                "Booking submitted with slot hold: booking_id=%s user_id=%s slot_start=%s slot_end=%s expires_at=%s",
                booking.id,
                user_id,
                slot_start_at_msk_naive,
                slot_end_at_msk_naive,
                expires_at_msk_naive,
            )
            return booking

    def confirm_booking_by_admin(self, booking_id: int, admin_telegram_user_id: int) -> BookingDecisionResult:
        with self._session_scope() as session:
            booking = self._repository.get_by_id(session=session, booking_id=booking_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            if booking.status not in {"pending_decision", "reschedule_requested"}:
                raise ValueError("Эту заявку нельзя подтвердить в текущем статусе.")
            if booking.status == "pending_decision":
                if booking.slot_start_at is None or booking.slot_end_at is None:
                    raise ValueError("У заявки отсутствует выбранный слот.")
                candidate_start = self._as_msk_naive(booking.slot_start_at)
                candidate_end = self._as_msk_naive(booking.slot_end_at)
            else:
                if booking.requested_new_slot_start_at is None or booking.requested_new_slot_end_at is None:
                    raise ValueError("Для переноса не выбран новый слот.")
                candidate_start = self._as_msk_naive(booking.requested_new_slot_start_at)
                candidate_end = self._as_msk_naive(booking.requested_new_slot_end_at)

            if self._repository.has_slot_conflict(
                session=session,
                slot_start_at=candidate_start,
                slot_end_at=candidate_end,
                exclude_booking_id=booking.id,
            ):
                logger.warning(
                    "Confirm blocked due to slot conflict: booking_id=%s slot_start=%s slot_end=%s",
                    booking.id,
                    candidate_start,
                    candidate_end,
                )
                raise ValueError("Слот больше недоступен. Подтвердить заявку нельзя.")

            user = self._user_repository.get_by_id(session=session, user_id=booking.user_id)
            if user is None:
                raise ValueError("Пользователь заявки не найден.")

            if booking.status == "reschedule_requested":
                # Move active slot to approved requested slot.
                self._repository.update_fields(
                    booking,
                    slot_start_at=booking.requested_new_slot_start_at,
                    slot_end_at=booking.requested_new_slot_end_at,
                    requested_new_slot_start_at=None,
                    requested_new_slot_end_at=None,
                )

            event_request = self._build_calendar_event_request(booking=booking, user=user)
            event_id = booking.calendar_event_id
            try:
                calendar_client = self._calendar_client_for_use()
                if booking.calendar_event_id:
                    calendar_client.update_event(booking.calendar_event_id, event_request)
                    event_id = booking.calendar_event_id
                else:
                    event_id = calendar_client.create_event(event_request)
            except Exception as exc:
                logger.warning(
                    "Calendar sync skipped on admin confirm: booking_id=%s reason=%s",
                    booking.id,
                    exc,
                )
            self._repository.update_fields(
                booking,
                calendar_event_id=event_id,
                expires_at=None,
            )
            self._transition_status(
                session=session,
                booking=booking,
                new_status="confirmed",
                changed_by=f"admin:{admin_telegram_user_id}",
            )
            session.flush()

            logger.info("Booking confirmed by admin: booking_id=%s event_id=%s", booking.id, event_id)
            return BookingDecisionResult(booking=booking, user=user)

    def reject_booking_by_admin(self, booking_id: int, admin_telegram_user_id: int) -> BookingDecisionResult:
        with self._session_scope() as session:
            booking = self._repository.get_by_id(session=session, booking_id=booking_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            if booking.status not in {"pending_decision", "reschedule_requested"}:
                raise ValueError("Эту заявку нельзя отклонить в текущем статусе.")

            user = self._user_repository.get_by_id(session=session, user_id=booking.user_id)
            if user is None:
                raise ValueError("Пользователь заявки не найден.")

            if booking.status == "reschedule_requested":
                new_status = self._status_after_reschedule_reject(booking)
                self._repository.update_fields(
                    booking,
                    requested_new_slot_start_at=None,
                    requested_new_slot_end_at=None,
                    expires_at=None,
                )
                self._transition_status(
                    session=session,
                    booking=booking,
                    new_status=new_status,
                    changed_by=f"admin:{admin_telegram_user_id}",
                )
            else:
                self._repository.update_fields(
                    booking,
                    slot_start_at=None,
                    slot_end_at=None,
                    expires_at=None,
                )
                self._transition_status(
                    session=session,
                    booking=booking,
                    new_status="rejected",
                    changed_by=f"admin:{admin_telegram_user_id}",
                )
            session.flush()
            logger.info("Booking rejected by admin: booking_id=%s slot_released=true", booking.id)
            return BookingDecisionResult(booking=booking, user=user)

    def cancel_confirmed_booking_by_admin(self, booking_id: int, admin_telegram_user_id: int) -> BookingDecisionResult:
        with self._session_scope() as session:
            booking = self._repository.get_by_id(session=session, booking_id=booking_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            if booking.status != "confirmed":
                raise ValueError("Отменить можно только подтвержденную заявку.")

            user = self._user_repository.get_by_id(session=session, user_id=booking.user_id)
            if user is None:
                raise ValueError("Пользователь заявки не найден.")

            if booking.calendar_event_id:
                self._calendar_client_for_use().delete_event(booking.calendar_event_id)
                logger.info(
                    "Calendar event removed due to admin cancellation: booking_id=%s event_id=%s",
                    booking.id,
                    booking.calendar_event_id,
                )

            self._repository.update_fields(
                booking,
                requested_new_slot_start_at=None,
                requested_new_slot_end_at=None,
                previous_slot_start_at=booking.previous_slot_start_at or booking.slot_start_at,
                previous_slot_end_at=booking.previous_slot_end_at or booking.slot_end_at,
                slot_start_at=None,
                slot_end_at=None,
                calendar_event_id=None,
                expires_at=None,
            )
            self._transition_status(
                session=session,
                booking=booking,
                new_status="canceled_by_admin",
                changed_by=f"admin:{admin_telegram_user_id}",
            )
            session.flush()
            logger.info(
                "Confirmed booking canceled by admin: booking_id=%s admin_telegram_user_id=%s",
                booking.id,
                admin_telegram_user_id,
            )
            return BookingDecisionResult(booking=booking, user=user)

    def cancel_booking_by_user(
        self,
        booking_id: int,
        user_id: int,
        user_telegram_user_id: int,
    ) -> Booking:
        with self._session_scope() as session:
            booking = self._repository.get_by_id_for_user(session, booking_id=booking_id, user_id=user_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            if booking.status not in {"draft", "pending_decision", "confirmed", "reschedule_requested"}:
                raise ValueError("Эту заявку нельзя отменить в текущем статусе.")

            if booking.calendar_event_id:
                try:
                    self._calendar_client_for_use().delete_event(booking.calendar_event_id)
                    logger.info(
                        "Calendar event removed due to user cancellation: booking_id=%s event_id=%s",
                        booking.id,
                        booking.calendar_event_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "Calendar event delete skipped for user cancellation: booking_id=%s event_id=%s reason=%s",
                        booking.id,
                        booking.calendar_event_id,
                        exc,
                    )

            self._repository.update_fields(
                booking,
                slot_start_at=None,
                slot_end_at=None,
                requested_new_slot_start_at=None,
                requested_new_slot_end_at=None,
                previous_slot_start_at=booking.previous_slot_start_at or booking.slot_start_at,
                previous_slot_end_at=booking.previous_slot_end_at or booking.slot_end_at,
                calendar_event_id=None,
                expires_at=None,
            )
            self._transition_status(
                session=session,
                booking=booking,
                new_status="canceled_by_user",
                changed_by=f"user:{user_telegram_user_id}",
            )
            session.flush()
            logger.info("Booking canceled by user: booking_id=%s user_id=%s", booking.id, user_id)
            return booking

    def request_reschedule_by_user(
        self,
        booking_id: int,
        user_id: int,
        user_telegram_user_id: int,
        requested_start_at_msk_naive: datetime,
        requested_end_at_msk_naive: datetime,
        expires_at_msk_naive: datetime,
    ) -> Booking:
        with self._session_scope() as session:
            booking = self._repository.get_by_id_for_user(session, booking_id=booking_id, user_id=user_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            if booking.status not in {"pending_decision", "confirmed"}:
                raise ValueError("Запросить перенос можно только для заявки в ожидании или подтвержденной.")
            if booking.slot_start_at is None or booking.slot_end_at is None:
                raise ValueError("У заявки нет активного слота для переноса.")

            old_start = self._as_msk_naive(booking.slot_start_at)
            old_end = self._as_msk_naive(booking.slot_end_at)
            if old_start == requested_start_at_msk_naive and old_end == requested_end_at_msk_naive:
                raise ValueError("Вы выбрали тот же слот. Выберите другое время.")

            if self._repository.has_slot_conflict(
                session=session,
                slot_start_at=requested_start_at_msk_naive,
                slot_end_at=requested_end_at_msk_naive,
                exclude_booking_id=booking.id,
            ):
                raise ValueError("Этот новый слот уже занят. Выберите другой.")

            self._repository.update_fields(
                booking,
                previous_slot_start_at=booking.slot_start_at,
                previous_slot_end_at=booking.slot_end_at,
                requested_new_slot_start_at=requested_start_at_msk_naive,
                requested_new_slot_end_at=requested_end_at_msk_naive,
                expires_at=expires_at_msk_naive,
            )
            self._transition_status(
                session=session,
                booking=booking,
                new_status="reschedule_requested",
                changed_by=f"user:{user_telegram_user_id}",
            )
            session.flush()
            logger.info(
                "Reschedule requested by user: booking_id=%s user_id=%s old_slot=%s..%s new_slot=%s..%s",
                booking.id,
                user_id,
                old_start,
                old_end,
                requested_start_at_msk_naive,
                requested_end_at_msk_naive,
            )
            return booking

    def rebook_after_closed_day_by_user(
        self,
        booking_id: int,
        user_id: int,
        user_telegram_user_id: int,
        slot_start_at_msk_naive: datetime,
        slot_end_at_msk_naive: datetime,
        expires_at_msk_naive: datetime,
    ) -> Booking:
        with self._session_scope() as session:
            booking = self._repository.get_by_id_for_user(session, booking_id=booking_id, user_id=user_id)
            if booking is None:
                raise ValueError("Заявка не найдена.")
            if booking.status != "canceled_by_admin":
                raise ValueError("Выбрать другое время можно только для отмененной администратором заявки.")
            if self._repository.has_slot_conflict(
                session=session,
                slot_start_at=slot_start_at_msk_naive,
                slot_end_at=slot_end_at_msk_naive,
                exclude_booking_id=booking.id,
            ):
                raise ValueError("Слот уже занят. Выберите другой.")

            self._repository.update_fields(
                booking,
                slot_start_at=slot_start_at_msk_naive,
                slot_end_at=slot_end_at_msk_naive,
                requested_new_slot_start_at=None,
                requested_new_slot_end_at=None,
                calendar_event_id=None,
                expires_at=expires_at_msk_naive,
            )
            self._transition_status(
                session=session,
                booking=booking,
                new_status="pending_decision",
                changed_by=f"user:{user_telegram_user_id}",
            )
            session.flush()
            logger.info(
                "Booking rebooked after closed day: booking_id=%s user_id=%s slot_start=%s slot_end=%s",
                booking.id,
                user_id,
                slot_start_at_msk_naive,
                slot_end_at_msk_naive,
            )
            return booking

    def _transition_status(
        self,
        session: Session,
        booking: Booking,
        new_status: str,
        changed_by: str,
    ) -> None:
        old_status = booking.status
        if old_status == new_status:
            return
        self._repository.update_fields(booking, status=new_status)
        self._status_history_repository.create_entry(
            session=session,
            booking_id=booking.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
        )

    def _calendar_client_for_use(self) -> CalendarClient:
        if self._calendar_client is not None:
            return self._calendar_client
        if self._settings is None:
            raise RuntimeError("Google Calendar client is not configured.")
        self._calendar_client = GoogleCalendarClient(
            service_account_file=self._settings.GOOGLE_SERVICE_ACCOUNT_FILE,
            calendar_id=self._settings.GOOGLE_CALENDAR_ID,
        )
        return self._calendar_client

    def _build_calendar_event_request(self, booking: Booking, user: User) -> CalendarEventRequest:
        if booking.slot_start_at is None or booking.slot_end_at is None:
            raise ValueError("У заявки отсутствует слот для события.")

        topic = booking.topic or "Без темы"
        user_name = user.name or user.telegram_display_name or f"User {user.id}"
        description = (
            f"Заявка #{booking.id}\n"
            f"Тема: {topic}\n"
            f"Формат: {booking.format or '—'}\n"
            f"Длительность: {booking.duration_minutes or '—'} минут\n"
            f"Пользователь: {user_name}\n"
            f"Телефон: {user.phone or '—'}\n"
            f"Email: {user.email or '—'}\n"
            f"Комментарий: {booking.comment or '—'}\n"
            f"Telegram user ID: {user.telegram_user_id}"
        )
        return CalendarEventRequest(
            summary=f"Встреча: {topic}",
            description=description,
            start_at=self._as_msk(booking.slot_start_at),
            end_at=self._as_msk(booking.slot_end_at),
            timezone="Europe/Moscow",
            attendee_email=user.email,
        )

    def _as_msk(self, dt_value: datetime) -> datetime:
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=MSK)
        return dt_value.astimezone(MSK)

    def _as_msk_naive(self, dt_value: datetime) -> datetime:
        return self._as_msk(dt_value).replace(tzinfo=None)

    def _status_after_reschedule_reject(self, booking: Booking) -> str:
        # If calendar event exists, booking was confirmed before reschedule request.
        if booking.calendar_event_id:
            return "confirmed"
        return "pending_decision"
