from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_booking_actions_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data=f"admin:confirm:{booking_id}",
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"admin:reject:{booking_id}",
                ),
            ]
        ]
    )


def admin_bookings_view_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 На подтверждении", callback_data="admin:view:queue"),
                InlineKeyboardButton(text="✅ Подтвержденные", callback_data="admin:view:confirmed"),
            ]
        ]
    )


def admin_confirmed_booking_actions_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Отменить",
                    callback_data=f"admin:cancel_confirmed:{booking_id}",
                )
            ]
        ]
    )
