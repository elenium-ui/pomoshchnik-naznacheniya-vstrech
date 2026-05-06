from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

BTN_OPEN_MINIAPP_INLINE = "🚀 Открыть Mini App"


def miniapp_open_inline_keyboard(miniapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_OPEN_MINIAPP_INLINE,
                    web_app=WebAppInfo(url=miniapp_url),
                )
            ]
        ]
    )
