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
    def __init__(self, event_id: str = "evt_123", should_fail: bool = False) -> None:
        self.event_id = event_id
        self.should_fail = should_fail
        self.requests: list[CalendarEventRequest] = []
        self.updated: list[tuple[str, CalendarEventRequest]] = []
        self.deleted: list[str] = []

    def create_event(self, request: CalendarEventRequest) -> str:
        self.requests.append(request)
        if self.should_fail:
            raise RuntimeError("calendar fail")
        return self.event_id

    def update_event(self, event_id: str, request: CalendarEventRequest) -> None:
        self.updated.append((event_id, request))
        if self.should_fail:
            raise RuntimeError("calendar fail")

    def delete_event(self, event_id: str) -> None:
        self.deleted.append(event_id)


def _create_user(session, telegram_user_id: int, email: str | None = None) -> User:
    user = User(
        telegram_user_id=telegram_user_id,
        telegram_username=f"u{telegram_user_id}",
        telegram_display_name=f"User {telegram_user_id}",
        name=f"User {telegram_user_id}",
        email=email,
        is_blocked=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(user)
    session.flush()
    return user


def test_admin_confirm_creates_calendar_event_and_history(tmp_path):
    db_file = tmp_path / "admin_confirm.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    fake_calendar = FakeCalendarClient(event_id="event_777")
    service = BookingService(sf, calendar_client=fake_calendar)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=111, email="guest@example.com")
        booking = Booking(
            user_id=user.id,
            topic="Тест встречи",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 10, 14, 0),
            slot_end_at=datetime(2026, 5, 10, 14, 30),
            status="pending_decision",
            expires_at=datetime(2026, 5, 13, 14, 0),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
    finally:
        session.close()

    result = service.confirm_booking_by_admin(booking_id=booking_id, admin_telegram_user_id=999)

    assert result.booking.status == "confirmed"
    assert result.booking.calendar_event_id == "event_777"
    assert result.booking.expires_at is None
    assert fake_calendar.requests
    assert fake_calendar.requests[0].attendee_email == "guest@example.com"

    session = sf()
    try:
        history = session.query(StatusHistory).filter(StatusHistory.booking_id == booking_id).all()
        assert len(history) == 1
        assert history[0].old_status == "pending_decision"
        assert history[0].new_status == "confirmed"
        assert history[0].changed_by == "admin:999"
    finally:
        session.close()
    engine.dispose()


def test_admin_reject_releases_slot_and_writes_history(tmp_path):
    db_file = tmp_path / "admin_reject.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    service = BookingService(sf, calendar_client=FakeCalendarClient())

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=222)
        booking = Booking(
            user_id=user.id,
            topic="Тест отклонения",
            format="офлайн",
            duration_minutes=60,
            slot_start_at=datetime(2026, 5, 12, 11, 0),
            slot_end_at=datetime(2026, 5, 12, 12, 0),
            status="pending_decision",
            expires_at=datetime(2026, 5, 15, 11, 0),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
    finally:
        session.close()

    result = service.reject_booking_by_admin(booking_id=booking_id, admin_telegram_user_id=555)

    assert result.booking.status == "rejected"
    assert result.booking.slot_start_at is None
    assert result.booking.slot_end_at is None
    assert result.booking.expires_at is None

    session = sf()
    try:
        history = session.query(StatusHistory).filter(StatusHistory.booking_id == booking_id).all()
        assert len(history) == 1
        assert history[0].old_status == "pending_decision"
        assert history[0].new_status == "rejected"
        assert history[0].changed_by == "admin:555"
    finally:
        session.close()
    engine.dispose()


def test_admin_confirm_rejects_when_slot_conflicts(tmp_path):
    db_file = tmp_path / "admin_conflict.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    fake_calendar = FakeCalendarClient()
    service = BookingService(sf, calendar_client=fake_calendar)

    session = sf()
    try:
        user1 = _create_user(session, telegram_user_id=333)
        user2 = _create_user(session, telegram_user_id=334)
        existing = Booking(
            user_id=user1.id,
            topic="Занятый слот",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 14, 15, 0),
            slot_end_at=datetime(2026, 5, 14, 15, 30),
            status="confirmed",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        candidate = Booking(
            user_id=user2.id,
            topic="Кандидат",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 14, 15, 0),
            slot_end_at=datetime(2026, 5, 14, 15, 30),
            status="pending_decision",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(existing)
        session.add(candidate)
        session.commit()
        candidate_id = candidate.id
    finally:
        session.close()

    with pytest.raises(ValueError):
        service.confirm_booking_by_admin(booking_id=candidate_id, admin_telegram_user_id=888)
    assert not fake_calendar.requests
    engine.dispose()


def test_admin_confirm_reschedule_updates_event_and_slot(tmp_path):
    db_file = tmp_path / "admin_reschedule_confirm.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    fake_calendar = FakeCalendarClient()
    service = BookingService(sf, calendar_client=fake_calendar)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=412, email="guest@example.com")
        booking = Booking(
            user_id=user.id,
            topic="Move me",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 20, 10, 0),
            slot_end_at=datetime(2026, 5, 20, 10, 30),
            requested_new_slot_start_at=datetime(2026, 5, 20, 12, 0),
            requested_new_slot_end_at=datetime(2026, 5, 20, 12, 30),
            status="reschedule_requested",
            calendar_event_id="evt_existing",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
    finally:
        session.close()

    result = service.confirm_booking_by_admin(booking_id=booking_id, admin_telegram_user_id=900)
    assert result.booking.status == "confirmed"
    assert result.booking.slot_start_at == datetime(2026, 5, 20, 12, 0)
    assert result.booking.requested_new_slot_start_at is None
    assert fake_calendar.updated
    assert fake_calendar.updated[0][0] == "evt_existing"
    assert not fake_calendar.requests
    engine.dispose()


def test_admin_reject_reschedule_restores_confirmed_status(tmp_path):
    db_file = tmp_path / "admin_reschedule_reject.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    service = BookingService(sf, calendar_client=FakeCalendarClient())

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=413)
        booking = Booking(
            user_id=user.id,
            topic="Reject move",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2026, 5, 21, 10, 0),
            slot_end_at=datetime(2026, 5, 21, 10, 30),
            requested_new_slot_start_at=datetime(2026, 5, 21, 11, 0),
            requested_new_slot_end_at=datetime(2026, 5, 21, 11, 30),
            status="reschedule_requested",
            calendar_event_id="evt_existing",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
    finally:
        session.close()

    result = service.reject_booking_by_admin(booking_id=booking_id, admin_telegram_user_id=901)
    assert result.booking.status == "confirmed"
    assert result.booking.slot_start_at == datetime(2026, 5, 21, 10, 0)
    assert result.booking.requested_new_slot_start_at is None
    engine.dispose()
