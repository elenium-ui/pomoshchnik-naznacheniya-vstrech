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
