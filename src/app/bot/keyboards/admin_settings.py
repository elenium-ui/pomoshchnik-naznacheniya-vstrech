from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_CLOSE_DAY = "📅 Закрыть день"
BTN_REOPEN_DAY = "🔓 Открыть день"
BTN_LIST_CLOSED_DAYS = "📋 Закрытые дни"
BTN_ADD_BLOCK = "⛔ Добавить блок"
BTN_MIN_LEAD = "⏱ Мин. срок подачи"
BTN_WINDOWS = "🗓 Окна работы"
BTN_BLOCK_USER = "🚫 Блокировать пользователя"
BTN_UNBLOCK_USER = "✅ Разблокировать пользователя"
BTN_BACK_ADMIN = "↩️ Назад в админ-меню"
BTN_ADD_WINDOW = "➕ Добавить окно работы"
BTN_CLEAR_WINDOWS = "🧹 Очистить окна работы"
BTN_ONE_TIME_WINDOW = "🧩 Разовое окно на дату"
BTN_DELETE_ONE_TIME_WINDOW = "🗑 Удалить разовое окно"
BTN_LIST_ONE_TIME_WINDOWS = "📋 Разовые окна"
BTN_BACK_SETTINGS = "↩️ Назад в настройки"
BTN_MANUAL_INPUT = "⌨️ Ввести вручную"
BTN_PICK_FROM_LIST = "🧭 Выбрать из списка"
BTN_BACK_WINDOWS = "↩️ Назад в окна работы"
BTN_CLEAR_WINDOWS_ALL = "🗑 Очистить все окна"

BTN_WEEKDAY_MON = "Пн"
BTN_WEEKDAY_TUE = "Вт"
BTN_WEEKDAY_WED = "Ср"
BTN_WEEKDAY_THU = "Чт"
BTN_WEEKDAY_FRI = "Пт"
BTN_WEEKDAY_SAT = "Сб"
BTN_WEEKDAY_SUN = "Вс"

WEEKDAY_BUTTONS = [
    BTN_WEEKDAY_MON,
    BTN_WEEKDAY_TUE,
    BTN_WEEKDAY_WED,
    BTN_WEEKDAY_THU,
    BTN_WEEKDAY_FRI,
    BTN_WEEKDAY_SAT,
    BTN_WEEKDAY_SUN,
]


def admin_settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CLOSE_DAY), KeyboardButton(text=BTN_REOPEN_DAY)],
            [KeyboardButton(text=BTN_LIST_CLOSED_DAYS), KeyboardButton(text=BTN_ADD_BLOCK)],
            [KeyboardButton(text=BTN_MIN_LEAD), KeyboardButton(text=BTN_WINDOWS)],
            [KeyboardButton(text=BTN_BLOCK_USER), KeyboardButton(text=BTN_UNBLOCK_USER)],
            [KeyboardButton(text=BTN_BACK_ADMIN)],
        ],
        resize_keyboard=True,
    )


def admin_windows_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD_WINDOW), KeyboardButton(text=BTN_CLEAR_WINDOWS)],
            [KeyboardButton(text=BTN_ONE_TIME_WINDOW), KeyboardButton(text=BTN_DELETE_ONE_TIME_WINDOW)],
            [KeyboardButton(text=BTN_LIST_ONE_TIME_WINDOWS)],
            [KeyboardButton(text=BTN_BACK_SETTINGS)],
        ],
        resize_keyboard=True,
    )


def admin_manual_or_picker_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PICK_FROM_LIST), KeyboardButton(text=BTN_MANUAL_INPUT)],
            [KeyboardButton(text=BTN_BACK_SETTINGS)],
        ],
        resize_keyboard=True,
    )


def admin_weekday_keyboard(*, include_clear_all: bool = False, back_to_windows: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=BTN_WEEKDAY_MON), KeyboardButton(text=BTN_WEEKDAY_TUE), KeyboardButton(text=BTN_WEEKDAY_WED)],
        [KeyboardButton(text=BTN_WEEKDAY_THU), KeyboardButton(text=BTN_WEEKDAY_FRI), KeyboardButton(text=BTN_WEEKDAY_SAT)],
        [KeyboardButton(text=BTN_WEEKDAY_SUN)],
    ]
    if include_clear_all:
        keyboard.append([KeyboardButton(text=BTN_CLEAR_WINDOWS_ALL)])
    keyboard.append([KeyboardButton(text=BTN_BACK_WINDOWS if back_to_windows else BTN_BACK_SETTINGS)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_manual_entry_keyboard(*, back_to_windows: bool = False) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BACK_WINDOWS if back_to_windows else BTN_BACK_SETTINGS)],
        ],
        resize_keyboard=True,
    )
