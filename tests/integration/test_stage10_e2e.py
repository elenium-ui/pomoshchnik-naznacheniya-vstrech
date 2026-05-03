from __future__ import annotations

from datetime import datetime, timedelta

from app.infrastructure.db.base import Base
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.admin.service import AdminService
from app.modules.bookings.service import BookingService
from app.modules.jobs.service import JobsService


class FakeCalendarClient:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.updated: list[str] = []
        self.deleted: list[str] = []

    def create_event(self, request) -> str:
        event_id = f"evt_{len(self.created) + 1}"
        self.created.append(event_id)
        return event_id

    def update_event(self, event_id: str, request) -> None:
        self.updated.append(event_id)

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


def _build_services(sf):
    fake_calendar = FakeCalendarClient()
    booking_service = BookingService(session_factory=sf, calendar_client=fake_calendar)
    admin_service = AdminService(
        session_factory=sf,
        google_service_account_file="secrets/dazzling-mote-495117-e9-d34b2f7f355b.json",
        google_calendar_id="test@example.com",
    )
    admin_service._calendar_client = fake_calendar  # noqa: SLF001
    jobs_service = JobsService(session_factory=sf)
    return booking_service, admin_service, jobs_service, fake_calendar


def test_stage10_user_create_and_admin_confirm(tmp_path):
    db_file = tmp_path / "s10_confirm.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    booking_service, _, _, fake_calendar = _build_services(sf)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=10001, email="u1@example.com")
        session.commit()
        user_id = user.id
    finally:
        session.close()

    draft = booking_service.create_draft(user_id=user_id)
    held = booking_service.hold_slot_and_submit(
        booking_id=draft.id,
        user_id=user_id,
        slot_start_at_msk_naive=datetime(2030, 1, 10, 10, 0),
        slot_end_at_msk_naive=datetime(2030, 1, 10, 10, 30),
        expires_at_msk_naive=datetime(2030, 1, 13, 10, 0),
    )
    assert held.status == "pending_decision"
    confirmed = booking_service.confirm_booking_by_admin(booking_id=held.id, admin_telegram_user_id=108776370)
    assert confirmed.booking.status == "confirmed"
    assert confirmed.booking.calendar_event_id is not None
    assert len(fake_calendar.created) == 1
    engine.dispose()


def test_stage10_user_create_and_admin_reject(tmp_path):
    db_file = tmp_path / "s10_reject.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    booking_service, _, _, _ = _build_services(sf)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=10002)
        session.commit()
        user_id = user.id
    finally:
        session.close()

    draft = booking_service.create_draft(user_id=user_id)
    held = booking_service.hold_slot_and_submit(
        booking_id=draft.id,
        user_id=user_id,
        slot_start_at_msk_naive=datetime(2030, 1, 11, 11, 0),
        slot_end_at_msk_naive=datetime(2030, 1, 11, 11, 30),
        expires_at_msk_naive=datetime(2030, 1, 14, 11, 0),
    )
    rejected = booking_service.reject_booking_by_admin(booking_id=held.id, admin_telegram_user_id=108776370)
    assert rejected.booking.status == "rejected"
    assert rejected.booking.slot_start_at is None
    engine.dispose()


def test_stage10_user_cancel_confirmed_meeting(tmp_path):
    db_file = tmp_path / "s10_cancel.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    booking_service, _, _, fake_calendar = _build_services(sf)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=10003)
        booking = Booking(
            user_id=user.id,
            topic="cancel",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2030, 1, 12, 12, 0),
            slot_end_at=datetime(2030, 1, 12, 12, 30),
            status="confirmed",
            calendar_event_id="evt_live",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
        user_id = user.id
    finally:
        session.close()

    canceled = booking_service.cancel_booking_by_user(
        booking_id=booking_id,
        user_id=user_id,
        user_telegram_user_id=10003,
    )
    assert canceled.status == "canceled_by_user"
    assert "evt_live" in fake_calendar.deleted
    engine.dispose()


def test_stage10_user_reschedule_request(tmp_path):
    db_file = tmp_path / "s10_reschedule.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    booking_service, _, _, _ = _build_services(sf)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=10004)
        booking = Booking(
            user_id=user.id,
            topic="move",
            format="онлайн",
            duration_minutes=30,
            slot_start_at=datetime(2030, 1, 13, 13, 0),
            slot_end_at=datetime(2030, 1, 13, 13, 30),
            status="confirmed",
            calendar_event_id="evt_move",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.commit()
        booking_id = booking.id
        user_id = user.id
    finally:
        session.close()

    moved = booking_service.request_reschedule_by_user(
        booking_id=booking_id,
        user_id=user_id,
        user_telegram_user_id=10004,
        requested_start_at_msk_naive=datetime(2030, 1, 14, 14, 0),
        requested_end_at_msk_naive=datetime(2030, 1, 14, 14, 30),
        expires_at_msk_naive=datetime(2030, 1, 17, 14, 0),
    )
    assert moved.status == "reschedule_requested"
    assert moved.slot_start_at == datetime(2030, 1, 13, 13, 0)
    assert moved.requested_new_slot_start_at == datetime(2030, 1, 14, 14, 0)
    engine.dispose()


def test_stage10_admin_close_day_with_confirmed_meeting(tmp_path):
    db_file = tmp_path / "s10_close_day.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    _, admin_service, _, fake_calendar = _build_services(sf)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=10005)
        session.add(
            Booking(
                user_id=user.id,
                topic="close day",
                format="офлайн",
                duration_minutes=60,
                slot_start_at=datetime(2030, 2, 1, 15, 0),
                slot_end_at=datetime(2030, 2, 1, 16, 0),
                status="confirmed",
                calendar_event_id="evt_close_day",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    canceled = admin_service.close_day(target_date=datetime(2030, 2, 1).date(), reason="maintenance")
    assert len(canceled) == 1
    assert "evt_close_day" in fake_calendar.deleted
    engine.dispose()


def test_stage10_admin_blocks_user_with_future_meetings(tmp_path):
    db_file = tmp_path / "s10_block.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    _, admin_service, _, fake_calendar = _build_services(sf)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=10006)
        session.add(
            Booking(
                user_id=user.id,
                topic="future",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2030, 2, 2, 10, 0),
                slot_end_at=datetime(2030, 2, 2, 10, 30),
                status="confirmed",
                calendar_event_id="evt_block",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    canceled = admin_service.block_user(telegram_user_id=10006)
    assert len(canceled) == 1
    assert "evt_block" in fake_calendar.deleted

    session = sf()
    try:
        user = session.query(User).filter(User.telegram_user_id == 10006).one()
        assert user.is_blocked is True
    finally:
        session.close()
    engine.dispose()


def test_stage10_ttl_auto_cancel(tmp_path):
    db_file = tmp_path / "s10_ttl.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    _, _, jobs_service, _ = _build_services(sf)

    now = datetime(2030, 2, 3, 12, 0)
    session = sf()
    try:
        user = _create_user(session, telegram_user_id=10007)
        session.add(
            Booking(
                user_id=user.id,
                topic="ttl",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2030, 2, 3, 11, 0),
                slot_end_at=datetime(2030, 2, 3, 11, 30),
                status="pending_decision",
                expires_at=now - timedelta(minutes=1),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    result = jobs_service.run_once(now_msk_naive=now)
    assert result.expired_processed == 1
    session = sf()
    try:
        booking = session.query(Booking).one()
        assert booking.status == "expired"
        assert booking.slot_start_at is None
    finally:
        session.close()
    engine.dispose()
