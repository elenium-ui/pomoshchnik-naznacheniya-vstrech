from __future__ import annotations

from datetime import datetime, time

from app.application.services.availability import AvailabilityService
from app.infrastructure.db.base import Base
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.user import User
from app.infrastructure.db.repositories.app_settings_repository import AppSettingsRepository
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.admin.service import AdminService


class DummyCalendarClient:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def create_event(self, request):  # pragma: no cover
        return "evt_dummy"

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


def _build_admin_service(sf, calendar: DummyCalendarClient) -> AdminService:
    service = AdminService(
        session_factory=sf,
        google_service_account_file="secrets/dazzling-mote-495117-e9-d34b2f7f355b.json",
        google_calendar_id="test@example.com",
    )
    service._calendar_client = calendar  # noqa: SLF001
    return service


def test_stage8_block_user_cancels_future_and_deletes_calendar(tmp_path):
    db_file = tmp_path / "stage8_block.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    calendar = DummyCalendarClient()
    admin_service = _build_admin_service(sf, calendar)

    session = sf()
    try:
        user = _create_user(session, 7001)
        session.add(
            Booking(
                user_id=user.id,
                topic="Future",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2030, 5, 10, 11, 0),
                slot_end_at=datetime(2030, 5, 10, 11, 30),
                status="confirmed",
                calendar_event_id="evt_future",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    canceled = admin_service.block_user(telegram_user_id=7001)
    assert len(canceled) == 1
    assert calendar.deleted == ["evt_future"]

    session = sf()
    try:
        user = session.query(User).filter(User.telegram_user_id == 7001).one()
        assert user.is_blocked is True
        booking = session.query(Booking).filter(Booking.user_id == user.id).one()
        assert booking.status == "canceled_by_admin"
        assert booking.slot_start_at is None
        assert booking.calendar_event_id is None
    finally:
        session.close()
    engine.dispose()


def test_stage8_close_day_cancels_bookings_and_returns_notifications(tmp_path):
    db_file = tmp_path / "stage8_close_day.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    calendar = DummyCalendarClient()
    admin_service = _build_admin_service(sf, calendar)

    target_date = datetime(2030, 7, 15).date()

    session = sf()
    try:
        user = _create_user(session, 7010)
        session.add(
            Booking(
                user_id=user.id,
                topic="Day close",
                format="офлайн",
                duration_minutes=60,
                slot_start_at=datetime(2030, 7, 15, 14, 0),
                slot_end_at=datetime(2030, 7, 15, 15, 0),
                status="confirmed",
                calendar_event_id="evt_close",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    notifications = admin_service.close_day(target_date=target_date, reason="Holiday")
    assert len(notifications) == 1
    assert notifications[0].user_telegram_user_id == 7010
    assert calendar.deleted == ["evt_close"]

    session = sf()
    try:
        booking = session.query(Booking).one()
        assert booking.status == "canceled_by_admin"
        assert booking.previous_slot_start_at is not None
        assert booking.slot_start_at is None
    finally:
        session.close()
    engine.dispose()


def test_stage8_min_lead_setting_applies_to_availability(tmp_path):
    db_file = tmp_path / "stage8_min_lead.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)

    settings_repo = AppSettingsRepository()
    session = sf()
    try:
        settings_repo.set_value(session, "min_lead_minutes", "1440")
        session.commit()
    finally:
        session.close()

    service = AvailabilityService(session_factory=sf)
    now = datetime(2026, 5, 4, 10, 0)
    slots = service.get_available_slots(duration_minutes=30, now=now)

    # With 24h lead time, same-day slots should be absent.
    same_day_slots = slots.get(now.date(), [])
    assert same_day_slots == []
    engine.dispose()


def test_stage8_search_filters_smoke(tmp_path):
    db_file = tmp_path / "stage8_search.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    admin_service = _build_admin_service(sf, DummyCalendarClient())

    session = sf()
    try:
        user = _create_user(session, 7099)
        user.email = "qa@example.com"
        session.add(
            Booking(
                user_id=user.id,
                topic="Filter me",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2031, 1, 20, 10, 0),
                slot_end_at=datetime(2031, 1, 20, 10, 30),
                status="pending_decision",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    rows = admin_service.search_bookings(status="pending_decision", email="qa@", telegram_user_id=7099)
    assert len(rows) == 1
    assert rows[0][0].topic == "Filter me"
    engine.dispose()


def test_stage8_set_window_and_time_block(tmp_path):
    db_file = tmp_path / "stage8_windows.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    admin_service = _build_admin_service(sf, DummyCalendarClient())

    rule = admin_service.set_working_window(weekday=2, start_at=time(9, 0), end_at=time(11, 0))
    assert rule.weekday == 2
    block = admin_service.add_time_block(
        target_date=datetime(2031, 1, 21).date(),
        start_at=time(9, 30),
        end_at=time(10, 0),
        comment="internal",
    )
    assert block.comment == "internal"
    removed = admin_service.clear_working_windows(weekday=2)
    assert removed >= 1
    engine.dispose()


def test_one_time_window_for_specific_date(tmp_path):
    db_file = tmp_path / "one_time_window.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    admin_service = _build_admin_service(sf, DummyCalendarClient())
    availability = AvailabilityService(session_factory=sf)

    # Saturday: by default there are no windows, but one-time window should open slots on this exact date.
    target_date = datetime(2026, 5, 9).date()
    admin_service.add_one_time_window(
        target_date=target_date,
        start_at=time(12, 0),
        end_at=time(13, 0),
        comment="special day",
    )

    slots = availability.get_available_slots(duration_minutes=30, now=datetime(2026, 5, 3, 9, 0))
    day_slots = slots.get(target_date, [])
    assert len(day_slots) == 2
    assert day_slots[0].start_at.hour == 12
    assert day_slots[1].start_at.hour == 12 and day_slots[1].start_at.minute == 30
    engine.dispose()


def test_one_time_window_delete_by_date(tmp_path):
    db_file = tmp_path / "one_time_window_delete.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    admin_service = _build_admin_service(sf, DummyCalendarClient())
    availability = AvailabilityService(session_factory=sf)

    target_date = datetime(2026, 5, 10).date()
    admin_service.add_one_time_window(target_date=target_date, start_at=time(12, 0), end_at=time(13, 0))
    removed = admin_service.remove_one_time_windows_by_date(target_date=target_date)
    assert removed == 1
    slots = availability.get_available_slots(duration_minutes=30, now=datetime(2026, 5, 3, 9, 0))
    assert slots.get(target_date, []) == []
    engine.dispose()


def test_reopen_day_and_list_closed_days(tmp_path):
    db_file = tmp_path / "closed_day_reopen.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    admin_service = _build_admin_service(sf, DummyCalendarClient())

    target_date = datetime(2026, 5, 12).date()
    admin_service.close_day(target_date=target_date, reason="Holiday")
    rows = admin_service.list_closed_days(limit=20)
    assert any(row.date == target_date for row in rows)

    reopened = admin_service.reopen_day(target_date=target_date)
    assert reopened is True
    reopened_again = admin_service.reopen_day(target_date=target_date)
    assert reopened_again is False
    engine.dispose()
