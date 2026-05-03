from __future__ import annotations

from datetime import datetime

import pytest

from app.infrastructure.calendar.google_calendar_client import CalendarEventRequest
from app.infrastructure.db.base import Base
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.status_history import StatusHistory
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.bookings.service import BookingService


class FakeCalendarClient:
    def __init__(self) -> None:
        self.created: list[CalendarEventRequest] = []
        self.deleted: list[str] = []

    def create_event(self, request: CalendarEventRequest) -> str:
        self.created.append(request)
        return "evt_fake"

    def delete_event(self, event_id: str) -> None:
        self.deleted.append(event_id)


def _create_user(session, telegram_user_id: int) -> User:
    user = User(
        telegram_user_id=telegram_user_id,
        telegram_username=f"u{telegram_user_id}",
        telegram_display_name=f"User {telegram_user_id}",
        name=f"User {telegram_user_id}",
        is_blocked=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(user)
    session.flush()
    return user


def test_cancel_confirmed_booking_deletes_calendar_event(tmp_path):
    db_file = tmp_path / "cancel_confirmed.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    fake_calendar = FakeCalendarClient()
    service = BookingService(sf, calendar_client=fake_calendar)

    session = sf()
    try:
        user = _create_user(session, 555)
        booking = Booking(
            user_id=user.id,
            topic="Confirmed",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 15, 10, 0),
            slot_end_at=datetime(2026, 5, 15, 10, 30),
            status="confirmed",
            calendar_event_id="evt_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
        user_id = user.id
    finally:
        session.close()

    canceled = service.cancel_booking_by_user(
        booking_id=booking_id,
        user_id=user_id,
        user_telegram_user_id=555,
    )

    assert canceled.status == "canceled_by_user"
    assert canceled.slot_start_at is None
    assert canceled.slot_end_at is None
    assert canceled.calendar_event_id is None
    assert fake_calendar.deleted == ["evt_123"]

    session = sf()
    try:
        history = session.query(StatusHistory).filter(StatusHistory.booking_id == booking_id).all()
        assert len(history) == 1
        assert history[0].old_status == "confirmed"
        assert history[0].new_status == "canceled_by_user"
    finally:
        session.close()
    engine.dispose()


def test_reschedule_request_holds_new_slot_and_keeps_old_slot(tmp_path):
    db_file = tmp_path / "reschedule_request.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    service = BookingService(sf, calendar_client=FakeCalendarClient())

    session = sf()
    try:
        user = _create_user(session, 777)
        booking = Booking(
            user_id=user.id,
            topic="Need move",
            format="офлайн",
            duration_minutes=60,
            slot_start_at=datetime(2026, 5, 16, 12, 0),
            slot_end_at=datetime(2026, 5, 16, 13, 0),
            status="confirmed",
            calendar_event_id="evt_777",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
        user_id = user.id
    finally:
        session.close()

    updated = service.request_reschedule_by_user(
        booking_id=booking_id,
        user_id=user_id,
        user_telegram_user_id=777,
        requested_start_at_msk_naive=datetime(2026, 5, 17, 14, 0),
        requested_end_at_msk_naive=datetime(2026, 5, 17, 15, 0),
        expires_at_msk_naive=datetime(2026, 5, 20, 14, 0),
    )

    assert updated.status == "reschedule_requested"
    assert updated.slot_start_at == datetime(2026, 5, 16, 12, 0)
    assert updated.slot_end_at == datetime(2026, 5, 16, 13, 0)
    assert updated.previous_slot_start_at == datetime(2026, 5, 16, 12, 0)
    assert updated.previous_slot_end_at == datetime(2026, 5, 16, 13, 0)
    assert updated.requested_new_slot_start_at == datetime(2026, 5, 17, 14, 0)
    assert updated.requested_new_slot_end_at == datetime(2026, 5, 17, 15, 0)

    session = sf()
    try:
        history = session.query(StatusHistory).filter(StatusHistory.booking_id == booking_id).all()
        assert len(history) == 1
        assert history[0].old_status == "confirmed"
        assert history[0].new_status == "reschedule_requested"
    finally:
        session.close()
    engine.dispose()


def test_reschedule_request_rejects_when_new_slot_conflicts(tmp_path):
    db_file = tmp_path / "reschedule_conflict.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    service = BookingService(sf, calendar_client=FakeCalendarClient())

    session = sf()
    try:
        user1 = _create_user(session, 1001)
        user2 = _create_user(session, 1002)
        occupied = Booking(
            user_id=user1.id,
            topic="occupied",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 18, 11, 0),
            slot_end_at=datetime(2026, 5, 18, 11, 30),
            status="pending_decision",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        source = Booking(
            user_id=user2.id,
            topic="source",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 18, 9, 0),
            slot_end_at=datetime(2026, 5, 18, 9, 30),
            status="confirmed",
            calendar_event_id="evt_source",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(occupied)
        session.add(source)
        session.commit()
        source_id = source.id
        user2_id = user2.id
    finally:
        session.close()

    with pytest.raises(ValueError):
        service.request_reschedule_by_user(
            booking_id=source_id,
            user_id=user2_id,
            user_telegram_user_id=1002,
            requested_start_at_msk_naive=datetime(2026, 5, 18, 11, 0),
            requested_end_at_msk_naive=datetime(2026, 5, 18, 11, 30),
            expires_at_msk_naive=datetime(2026, 5, 21, 11, 0),
        )
    engine.dispose()
