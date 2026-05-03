from app.infrastructure.db.base import Base
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.users.service import UserService


def test_user_created_on_first_entry(tmp_path):
    db_file = tmp_path / "entry.db"
    engine = build_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    service = UserService(session_factory=session_factory)
    created = service.ensure_user_from_telegram(
        telegram_user_id=777,
        telegram_username="tester",
        telegram_display_name="Test User",
    )

    session = session_factory()
    try:
        user = session.query(User).filter(User.telegram_user_id == 777).one_or_none()
        assert user is not None
        assert user.id == created.id
        assert user.telegram_username == "tester"
        assert user.name == "Test User"
    finally:
        session.close()
        engine.dispose()
