from app.application.services.roles import resolve_user_role
from app.domain.enums.user_role import UserRole


def test_resolve_user_role_returns_admin_for_matching_id():
    assert resolve_user_role(telegram_user_id=42, admin_user_id=42) == UserRole.ADMIN


def test_resolve_user_role_returns_user_for_non_matching_id():
    assert resolve_user_role(telegram_user_id=100, admin_user_id=42) == UserRole.USER
