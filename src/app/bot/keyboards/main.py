from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_NEW_BOOKING = "📝 Новая заявка"
BTN_MY_BOOKINGS = "📂 Мои заявки"
BTN_OPEN_MINIAPP = "📱 Открыть Mini App"
BTN_ADMIN_BOOKINGS = "📥 Админ: заявки"
BTN_ADMIN_SETTINGS = "⚙️ Админ: настройки"


def user_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_OPEN_MINIAPP)],
            [KeyboardButton(text=BTN_NEW_BOOKING)],
            [KeyboardButton(text=BTN_MY_BOOKINGS)],
        ],
        resize_keyboard=True,
    )


def admin_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_OPEN_MINIAPP)],
            [KeyboardButton(text=BTN_NEW_BOOKING)],
            [KeyboardButton(text=BTN_MY_BOOKINGS)],
            [KeyboardButton(text=BTN_ADMIN_BOOKINGS)],
            [KeyboardButton(text=BTN_ADMIN_SETTINGS)],
        ],
        resize_keyboard=True,
    )
