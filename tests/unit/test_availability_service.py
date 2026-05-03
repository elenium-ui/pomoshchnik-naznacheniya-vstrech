from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.application.services.availability import AvailabilityPolicy, AvailabilityService
from app.domain.models.availability import TimeInterval
from app.infrastructure.db.base import Base
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.closed_date import ClosedDate
from app.infrastructure.db.models.time_block import TimeBlock
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import build_engine, build_session_factory


MSK = ZoneInfo("Europe/Moscow")


class StubBusyProvider:
    def __init__(self, intervals=None):
        self._intervals = intervals or []

    def get_busy_intervals(self, start_at: datetime, end_at: datetime):
        return self._intervals


def _make_service(tmp_path, busy_provider=None):
    db_file = tmp_path / "availability_unit.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    policy = AvailabilityPolicy(
        timezone="Europe/Moscow",
        slot_step_minutes=30,
        horizon_days=35,
        min_lead_minutes=60,
        daily_limit=4,
    )
    service = AvailabilityService(
        session_factory=session_factory,
        policy=policy,
        busy_provider=busy_provider or StubBusyProvider(),
    )
    return service, session_factory, engine


def test_default_windows_step_and_min_lead(tmp_path):
    service, _, engine = _make_service(tmp_path)

    now = datetime(2026, 5, 4, 9, 10, tzinfo=MSK)  # Monday
    slots = service.get_available_slots(duration_minutes=30, now=now)

    day = date(2026, 5, 4)
    assert day in slots
    assert slots[day][0].start_at.strftime("%H:%M") == "10:30"

    for slot in slots[day]:
        assert slot.start_at.minute in {0, 30}

    engine.dispose()


def test_closed_date_excludes_day(tmp_path):
    service, session_factory, engine = _make_service(tmp_path)

    with session_factory() as session:
        session.add(ClosedDate(date=date(2026, 5, 4), reason="holiday"))
        session.commit()

    now = datetime(2026, 5, 4, 8, 0, tzinfo=MSK)
    slots = service.get_available_slots(duration_minutes=30, now=now)

    assert date(2026, 5, 4) not in slots
    engine.dispose()


def test_time_block_excludes_overlapping_slots(tmp_path):
    service, session_factory, engine = _make_service(tmp_path)

    with session_factory() as session:
        session.add(
            TimeBlock(
                date=date(2026, 5, 4),
                start_time=time(10, 30),
                end_time=time(11, 30),
                comment="internal",
                created_at=datetime.utcnow(),
            )
        )
        session.commit()

    now = datetime(2026, 5, 4, 8, 0, tzinfo=MSK)
    slots = service.get_available_slots(duration_minutes=30, now=now)
    starts = [slot.start_at.strftime("%H:%M") for slot in slots[date(2026, 5, 4)]]

    assert "10:30" not in starts
    assert "11:00" not in starts
    engine.dispose()


def test_occupied_booking_excludes_slot(tmp_path):
    service, session_factory, engine = _make_service(tmp_path)

    with session_factory() as session:
        user = User(
            telegram_user_id=999,
            telegram_username="u",
            telegram_display_name="User",
            name="User",
            is_blocked=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(user)
        session.flush()

        session.add(
            Booking(
                user_id=user.id,
                topic="topic",
                format="онлайн",
                duration_minutes=30,
                slot_start_at=datetime(2026, 5, 4, 14, 0),
                slot_end_at=datetime(2026, 5, 4, 14, 30),
                status="confirmed",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()

    now = datetime(2026, 5, 4, 8, 0, tzinfo=MSK)
    slots = service.get_available_slots(duration_minutes=30, now=now)
    starts = [slot.start_at.strftime("%H:%M") for slot in slots[date(2026, 5, 4)]]

    assert "14:00" not in starts
    engine.dispose()


def test_daily_limit_excludes_day(tmp_path):
    service, session_factory, engine = _make_service(tmp_path)

    with session_factory() as session:
        user = User(
            telegram_user_id=1001,
            telegram_username="u2",
            telegram_display_name="User2",
            name="User2",
            is_blocked=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(user)
        session.flush()

        booked = [
            (time(10, 0), time(10, 30)),
            (time(10, 30), time(11, 0)),
            (time(11, 0), time(11, 30)),
            (time(14, 0), time(14, 30)),
        ]
        for start_t, end_t in booked:
            session.add(
                Booking(
                    user_id=user.id,
                    topic="topic",
                    format="онлайн",
                    duration_minutes=30,
                    slot_start_at=datetime.combine(date(2026, 5, 4), start_t),
                    slot_end_at=datetime.combine(date(2026, 5, 4), end_t),
                    status="confirmed",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )

        session.commit()

    now = datetime(2026, 5, 4, 8, 0, tzinfo=MSK)
    slots = service.get_available_slots(duration_minutes=30, now=now)

    assert date(2026, 5, 4) not in slots
    engine.dispose()


def test_external_busy_provider_blocks_slots(tmp_path):
    busy_provider = StubBusyProvider(
        intervals=[
            TimeInterval(
                start_at=datetime(2026, 5, 4, 15, 0, tzinfo=MSK),
                end_at=datetime(2026, 5, 4, 15, 30, tzinfo=MSK),
                source="calendar",
            )
        ]
    )
    service, _, engine = _make_service(tmp_path, busy_provider=busy_provider)

    now = datetime(2026, 5, 4, 8, 0, tzinfo=MSK)
    slots = service.get_available_slots(duration_minutes=30, now=now)

    starts = [slot.start_at.strftime("%H:%M") for slot in slots[date(2026, 5, 4)]]
    assert "15:00" not in starts
    engine.dispose()


def test_horizon_not_exceed_35_days(tmp_path):
    service, _, engine = _make_service(tmp_path)

    now = datetime(2026, 5, 4, 8, 0, tzinfo=MSK)
    slots = service.get_available_slots(duration_minutes=30, now=now)

    if slots:
        assert max(slots.keys()) <= now.date() + timedelta(days=35)
    engine.dispose()
