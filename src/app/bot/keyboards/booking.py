from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.domain.enums.booking import DURATION_OPTIONS

BTN_CANCEL = "❌ Отмена"
BTN_SKIP = "⏭ Пропустить"
BTN_REFRESH_SLOTS = "🔄 Обновить слоты"
BTN_BACK = "⬅️ Назад"


def keep_name_keyboard(current_name: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"Оставить: {current_name}")],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def keep_email_keyboard(current_email: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"Оставить: {current_email}")],
            [KeyboardButton(text=BTN_SKIP)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def format_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="онлайн"), KeyboardButton(text="офлайн")],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def duration_keyboard() -> ReplyKeyboardMarkup:
    row = [KeyboardButton(text=f"{value} минут") for value in DURATION_OPTIONS]
    return ReplyKeyboardMarkup(
        keyboard=[row[:3], row[3:], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def optional_skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def slot_selection_keyboard(
    slot_labels: list[str],
    *,
    add_back: bool = False,
    columns: int = 2,
) -> ReplyKeyboardMarkup:
    columns = max(1, columns)
    keyboard = []
    row: list[KeyboardButton] = []

    for label in slot_labels:
        row.append(KeyboardButton(text=label))
        if len(row) == columns:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([KeyboardButton(text=BTN_REFRESH_SLOTS)])
    if add_back:
        keyboard.append([KeyboardButton(text=BTN_BACK)])
    keyboard.append([KeyboardButton(text=BTN_CANCEL)])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
