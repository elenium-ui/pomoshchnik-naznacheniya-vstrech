from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.infrastructure.db.base import Base
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.status_history import StatusHistory
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.jobs.runner import run_jobs_once_with_notifications
from app.modules.jobs.service import JobsService


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


def test_ttl_auto_cancel_releases_slot_and_marks_expired(tmp_path):
    db_file = tmp_path / "jobs_ttl.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    jobs_service = JobsService(session_factory=sf)

    now = datetime(2026, 6, 1, 12, 0)
    session = sf()
    try:
        user = _create_user(session, telegram_user_id=9011)
        session.add(
            Booking(
                user_id=user.id,
                topic="TTL",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2026, 6, 1, 11, 0),
                slot_end_at=datetime(2026, 6, 1, 11, 30),
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
    assert len(result.notices) == 1
    assert result.notices[0].user_telegram_user_id == 9011

    session = sf()
    try:
        booking = session.query(Booking).one()
        assert booking.status == "expired"
        assert booking.slot_start_at is None
        assert booking.slot_end_at is None
        assert booking.expires_at is None

        rows = session.query(StatusHistory).all()
        assert len(rows) == 1
        assert rows[0].old_status == "pending_decision"
        assert rows[0].new_status == "expired"
        assert rows[0].changed_by == "system:ttl"
    finally:
        session.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_runner_sends_ttl_notification(tmp_path):
    db_file = tmp_path / "jobs_notify.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    jobs_service = JobsService(session_factory=sf)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=9012)
        session.add(
            Booking(
                user_id=user.id,
                topic="Notify",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2026, 6, 2, 9, 0),
                slot_end_at=datetime(2026, 6, 2, 9, 30),
                status="pending_decision",
                expires_at=datetime.utcnow() - timedelta(days=1),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    sent: list[tuple[int, str]] = []

    async def fake_notify(tg_id: int, text: str) -> None:
        sent.append((tg_id, text))

    result = await run_jobs_once_with_notifications(jobs_service=jobs_service, notify_user=fake_notify)
    assert result.expired_processed == 1
    assert len(sent) == 1
    assert sent[0][0] == 9012
    assert "автоматически отменена" in sent[0][1]
    engine.dispose()


def test_status_history_cleanup_older_than_30_days(tmp_path):
    db_file = tmp_path / "jobs_cleanup.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    jobs_service = JobsService(session_factory=sf)

    now = datetime(2026, 6, 3, 10, 0)
    session = sf()
    try:
        user = _create_user(session, telegram_user_id=9013)
        booking = Booking(
            user_id=user.id,
            topic="Cleanup",
            format="онлайн",
            duration_minutes=30,
            status="draft",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(booking)
        session.flush()
        session.add(
            StatusHistory(
                booking_id=booking.id,
                old_status="draft",
                new_status="pending_decision",
                changed_by="test",
                changed_at=now - timedelta(days=31),
            )
        )
        session.add(
            StatusHistory(
                booking_id=booking.id,
                old_status="pending_decision",
                new_status="expired",
                changed_by="test",
                changed_at=now - timedelta(days=5),
            )
        )
        session.commit()
    finally:
        session.close()

    result = jobs_service.run_once(now_msk_naive=now)
    assert result.status_history_deleted == 1

    session = sf()
    try:
        rows = session.query(StatusHistory).all()
        assert len(rows) == 1
        assert rows[0].new_status == "expired"
    finally:
        session.close()
    engine.dispose()


def test_repeated_run_does_not_duplicate_ttl_processing(tmp_path):
    db_file = tmp_path / "jobs_idempotent.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sf = build_session_factory(engine)
    jobs_service = JobsService(session_factory=sf)
    now = datetime(2026, 6, 4, 10, 0)

    session = sf()
    try:
        user = _create_user(session, telegram_user_id=9014)
        session.add(
            Booking(
                user_id=user.id,
                topic="Idempotent",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2026, 6, 4, 9, 0),
                slot_end_at=datetime(2026, 6, 4, 9, 30),
                status="pending_decision",
                expires_at=now - timedelta(minutes=1),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    first = jobs_service.run_once(now_msk_naive=now)
    second = jobs_service.run_once(now_msk_naive=now)
    assert first.expired_processed == 1
    assert second.expired_processed == 0
    assert len(second.notices) == 0
    engine.dispose()
