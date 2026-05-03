from app.application.services.booking_validation import requires_alternative_contact
from app.infrastructure.db.base import Base
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.bookings.service import BookingService
from app.modules.users.service import UserService


def test_booking_draft_created_and_updated(tmp_path):
    db_file = tmp_path / "booking_flow.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    user_service = UserService(session_factory)
    booking_service = BookingService(session_factory)

    user = user_service.ensure_user_from_telegram(
        telegram_user_id=123,
        telegram_username=None,
        telegram_display_name="Test Admin",
    )

    draft = booking_service.create_draft(user_id=user.id)
    assert draft.status == "draft"

    booking_service.update_booking_fields(
        booking_id=draft.id,
        user_id=user.id,
        topic="Тестовая встреча",
        format="онлайн",
        duration_minutes=30,
        comment="Комментарий",
        status="draft",
    )

    session = session_factory()
    try:
        saved = session.query(Booking).filter(Booking.id == draft.id).one()
        assert saved.topic == "Тестовая встреча"
        assert saved.format == "онлайн"
        assert saved.duration_minutes == 30
        assert saved.status == "draft"
    finally:
        session.close()

    engine.dispose()


def test_requires_alt_contact_for_user_without_username_and_email(tmp_path):
    db_file = tmp_path / "booking_contact.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    user_service = UserService(session_factory)
    user = user_service.ensure_user_from_telegram(
        telegram_user_id=555,
        telegram_username=None,
        telegram_display_name="No Username",
    )

    session = session_factory()
    try:
        saved = session.query(User).filter(User.id == user.id).one()
        assert saved.telegram_username is None
        assert requires_alternative_contact(has_username=False, email=saved.email) is True
    finally:
        session.close()

    engine.dispose()
