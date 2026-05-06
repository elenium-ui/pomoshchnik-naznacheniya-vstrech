from app.bot.keyboards.main import BTN_OPEN_MINIAPP, admin_main_keyboard, user_main_keyboard
from app.bot.keyboards.miniapp import BTN_OPEN_MINIAPP_INLINE, miniapp_open_inline_keyboard


def _button_texts(reply_markup) -> list[str]:
    return [button.text for row in reply_markup.keyboard for button in row]


def test_main_keyboards_contain_open_miniapp_button() -> None:
    user_texts = _button_texts(user_main_keyboard())
    admin_texts = _button_texts(admin_main_keyboard())

    assert BTN_OPEN_MINIAPP in user_texts
    assert BTN_OPEN_MINIAPP in admin_texts


def test_inline_miniapp_keyboard_contains_web_app_url() -> None:
    miniapp_url = "https://miniapp.example.com"
    keyboard = miniapp_open_inline_keyboard(miniapp_url)

    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.text == BTN_OPEN_MINIAPP_INLINE
    assert button.web_app is not None
    assert button.web_app.url == miniapp_url
