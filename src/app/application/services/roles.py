from app.domain.enums.user_role import UserRole


def resolve_user_role(telegram_user_id: int, admin_user_id: int) -> UserRole:
    return UserRole.ADMIN if telegram_user_id == admin_user_id else UserRole.USER
