from datetime import datetime, timedelta

import pytest

from app.infrastructure.db.base import Base
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.bookings.service import BookingService


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


def test_hold_slot_sets_pending_and_ttl(tmp_path):
    db_file = tmp_path / "hold_slot.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)

    service = BookingService(sf)

    session = sf()
    try:
        user = _create_user(session, 100)
        session.commit()
        user_id = user.id
    finally:
        session.close()

    draft = service.create_draft(user_id=user_id)

    start_at = datetime(2026, 5, 10, 14, 0)
    end_at = datetime(2026, 5, 10, 14, 30)
    expires = datetime(2026, 5, 13, 14, 0)

    submitted = service.hold_slot_and_submit(
        booking_id=draft.id,
        user_id=user_id,
        slot_start_at_msk_naive=start_at,
        slot_end_at_msk_naive=end_at,
        expires_at_msk_naive=expires,
    )

    assert submitted.status == "pending_decision"
    assert submitted.slot_start_at == start_at
    assert submitted.slot_end_at == end_at
    assert submitted.expires_at == expires

    engine.dispose()


def test_hold_slot_rejects_conflict(tmp_path):
    db_file = tmp_path / "hold_conflict.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)

    service = BookingService(sf)

    session = sf()
    try:
        user1 = _create_user(session, 201)
        user2 = _create_user(session, 202)

        session.add(
            Booking(
                user_id=user1.id,
                topic="A",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2026, 5, 10, 14, 0),
                slot_end_at=datetime(2026, 5, 10, 14, 30),
                status="pending_decision",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
        user2_id = user2.id
    finally:
        session.close()

    draft = service.create_draft(user_id=user2_id)

    with pytest.raises(ValueError):
        service.hold_slot_and_submit(
            booking_id=draft.id,
            user_id=user2_id,
            slot_start_at_msk_naive=datetime(2026, 5, 10, 14, 0),
            slot_end_at_msk_naive=datetime(2026, 5, 10, 14, 30),
            expires_at_msk_naive=datetime(2026, 5, 13, 14, 0),
        )

    engine.dispose()


def test_count_future_active_for_limit(tmp_path):
    db_file = tmp_path / "limit_count.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)

    service = BookingService(sf)

    now = datetime(2026, 5, 5, 12, 0)

    session = sf()
    try:
        user = _create_user(session, 303)

        for i in range(7):
            session.add(
                Booking(
                    user_id=user.id,
                    topic=f"B{i}",
                    format="онлайн",
                    duration_minutes=30,
                    slot_start_at=now + timedelta(days=1, minutes=i * 30),
                    slot_end_at=now + timedelta(days=1, minutes=(i + 1) * 30),
                    status="pending_decision",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )

        # Draft without slot should not count.
        session.add(
            Booking(
                user_id=user.id,
                topic="draft",
                format="онлайн",
                duration_minutes=30,
                status="draft",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )

        session.commit()
        user_id = user.id
    finally:
        session.close()

    count = service.count_future_active_for_limit(user_id=user_id, now_msk_naive=now)
    assert count == 7

    engine.dispose()
