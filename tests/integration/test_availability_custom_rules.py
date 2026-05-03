from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.application.services.availability import AvailabilityPolicy, AvailabilityService
from app.infrastructure.db.base import Base
from app.infrastructure.db.models.availability_rule import AvailabilityRule
from app.infrastructure.db.session import build_engine, build_session_factory


MSK = ZoneInfo("Europe/Moscow")


def test_custom_rule_overrides_default_windows(tmp_path):
    db_file = tmp_path / "availability_integration.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        # Tuesday only: 09:00-10:00
        session.add(
            AvailabilityRule(
                weekday=1,
                start_time=time(9, 0),
                end_time=time(10, 0),
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()

    service = AvailabilityService(
        session_factory=session_factory,
        policy=AvailabilityPolicy(),
    )

    now = datetime(2026, 5, 5, 7, 0, tzinfo=MSK)  # Tuesday
    slots = service.get_available_slots(duration_minutes=30, now=now)

    day = date(2026, 5, 5)
    assert day in slots
    starts = [slot.start_at.strftime("%H:%M") for slot in slots[day]]
    assert starts == ["09:00", "09:30"]

    engine.dispose()
