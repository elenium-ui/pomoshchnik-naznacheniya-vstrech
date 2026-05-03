from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def user_booking_open_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть",
                    callback_data=f"user:open:{booking_id}",
                )
            ]
        ]
    )


def user_booking_actions_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=f"user:cancel:{booking_id}",
                ),
                InlineKeyboardButton(
                    text="Перенести",
                    callback_data=f"user:reschedule:{booking_id}",
                ),
            ]
        ]
    )


def choose_other_time_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Выбрать другое время",
                    callback_data=f"user:choose_other_time:{booking_id}",
                )
            ]
        ]
    )
