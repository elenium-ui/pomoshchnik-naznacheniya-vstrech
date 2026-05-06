from __future__ import annotations

import logging
from datetime import date as dt_date
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.orm import sessionmaker

from app.application.services.availability import AvailabilityService
from app.application.services.booking_validation import (
    parse_optional_comment,
    parse_optional_email,
    requires_alternative_contact,
    validate_duration,
    validate_meeting_format,
    validate_name,
    validate_phone,
    validate_topic,
)
from app.bot.keyboards.booking import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_REFRESH_SLOTS,
    BTN_SKIP,
    duration_keyboard,
    format_keyboard,
    keep_email_keyboard,
    keep_name_keyboard,
    optional_skip_keyboard,
    slot_selection_keyboard,
)
from app.bot.keyboards.admin_booking import (
    admin_booking_actions_keyboard,
    admin_bookings_view_keyboard,
    admin_confirmed_booking_actions_keyboard,
)
from app.bot.keyboards.admin_settings import (
    BTN_ADD_BLOCK,
    BTN_ADD_WINDOW,
    BTN_BACK_ADMIN,
    BTN_BACK_SETTINGS,
    BTN_BACK_WINDOWS,
    BTN_BLOCK_USER,
    BTN_CLEAR_WINDOWS,
    BTN_CLEAR_WINDOWS_ALL,
    BTN_CLOSE_DAY,
    BTN_DELETE_ONE_TIME_WINDOW,
    BTN_LIST_CLOSED_DAYS,
    BTN_LIST_ONE_TIME_WINDOWS,
    BTN_MANUAL_INPUT,
    BTN_MIN_LEAD,
    BTN_REOPEN_DAY,
    BTN_PICK_FROM_LIST,
    BTN_ONE_TIME_WINDOW,
    BTN_WEEKDAY_FRI,
    BTN_WEEKDAY_MON,
    BTN_WEEKDAY_SAT,
    BTN_WEEKDAY_SUN,
    BTN_WEEKDAY_THU,
    BTN_WEEKDAY_TUE,
    BTN_WEEKDAY_WED,
    BTN_UNBLOCK_USER,
    BTN_WINDOWS,
    admin_manual_entry_keyboard,
    admin_manual_or_picker_keyboard,
    admin_settings_keyboard,
    admin_weekday_keyboard,
    admin_windows_keyboard,
)
from app.bot.keyboards.main import (
    BTN_ADMIN_BOOKINGS,
    BTN_ADMIN_SETTINGS,
    BTN_MY_BOOKINGS,
    BTN_NEW_BOOKING,
    admin_main_keyboard,
    user_main_keyboard,
)
from app.bot.keyboards.user_booking import (
    choose_other_time_keyboard,
    user_booking_actions_keyboard,
    user_booking_open_keyboard,
)
from app.bot.states.booking_form import BookingForm
from app.config import Settings
from app.domain.enums.user_role import UserRole
from app.modules.bookings.service import BookingService
from app.modules.admin.service import AdminService
from app.modules.users.service import UserService

logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")
WEEKDAY_NAMES = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}
WEEKDAY_LABEL_TO_INDEX = {
    BTN_WEEKDAY_MON: 0,
    BTN_WEEKDAY_TUE: 1,
    BTN_WEEKDAY_WED: 2,
    BTN_WEEKDAY_THU: 3,
    BTN_WEEKDAY_FRI: 4,
    BTN_WEEKDAY_SAT: 5,
    BTN_WEEKDAY_SUN: 6,
}


def _main_menu_for(role: UserRole):
    return admin_main_keyboard() if role == UserRole.ADMIN else user_main_keyboard()


def _format_slot(start_at: datetime, end_at: datetime) -> str:
    return f"{start_at.strftime('%d.%m %H:%M')} - {end_at.strftime('%H:%M')} (MSK)"


def _slot_key(start_at: datetime) -> str:
    return start_at.strftime("%Y-%m-%d %H:%M")


def _parse_date(raw: str) -> dt_date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _parse_time(raw: str) -> dt_time:
    return datetime.strptime(raw, "%H:%M").time()


def _is_new_booking_text(text: str) -> bool:
    return text in {BTN_NEW_BOOKING, "Новая заявка", "/new_booking"}


def _is_my_bookings_text(text: str) -> bool:
    return text in {BTN_MY_BOOKINGS, "Мои заявки", "/my_bookings"}


def _is_admin_bookings_text(text: str) -> bool:
    return text in {BTN_ADMIN_BOOKINGS, "Админ: заявки", "/admin_bookings"}


def _is_admin_settings_text(text: str) -> bool:
    return text in {BTN_ADMIN_SETTINGS, "Админ: настройки", "/admin_settings"}


def _is_cancel_text(text: str) -> bool:
    return text in {BTN_CANCEL, "Отмена", "/cancel"}


def _is_skip_text(text: str) -> bool:
    return text in {BTN_SKIP, "Пропустить"}


def _is_refresh_slots_text(text: str) -> bool:
    return text in {BTN_REFRESH_SLOTS, "Обновить слоты"}


def _is_back_text(text: str) -> bool:
    lowered = text.strip().lower()
    return text == BTN_BACK or lowered == "назад" or "назад" in lowered


def _build_future_week_options(weeks_count: int = 8) -> dict[str, str]:
    today = datetime.now(MSK).date()
    first_monday = today - timedelta(days=today.weekday())
    week_options: dict[str, str] = {}
    for idx in range(weeks_count):
        week_start = first_monday + timedelta(days=idx * 7)
        week_end = week_start + timedelta(days=6)
        label = f"Неделя {week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')}"
        week_options[label] = week_start.isoformat()
    return week_options


def _build_week_days_options(week_start: dt_date) -> dict[str, str]:
    day_options: dict[str, str] = {}
    for offset in range(7):
        target = week_start + timedelta(days=offset)
        weekday = WEEKDAY_NAMES.get(target.weekday(), str(target.weekday()))
        day_options[f"{weekday} {target.strftime('%d.%m.%Y')}"] = target.isoformat()
    return day_options


def _slots_word(count: int) -> str:
    n = abs(count) % 100
    if 11 <= n <= 14:
        return "слотов"
    last = n % 10
    if last == 1:
        return "слот"
    if 2 <= last <= 4:
        return "слота"
    return "слотов"


def _format_duration(minutes: int | None) -> str:
    if not minutes:
        return "—"
    return f"{minutes} мин."


def _user_status_badge(status: str) -> str:
    mapping = {
        "draft": "📝 Черновик",
        "pending_decision": "🟡 На подтверждении",
        "confirmed": "✅ Подтверждена",
        "rejected": "❌ Не подтверждена",
        "cancelled_by_user": "🚫 Отменена",
        "cancelled_by_admin": "🚫 Отменена",
        "canceled_by_admin": "🚫 Отменена",
        "reschedule_pending_decision": "🔁 Перенос на подтверждении",
    }
    return mapping.get(status, "ℹ️ В обработке")


def _format_booking_card_line(booking, include_status_badge: bool = True) -> str:
    slot_line = "—"
    if booking.slot_start_at and booking.slot_end_at:
        start_at = booking.slot_start_at
        end_at = booking.slot_end_at
        slot_line = f"{start_at.strftime('%d.%m %H:%M')} - {end_at.strftime('%H:%M')}"

    lines = []
    if include_status_badge:
        lines.append(_user_status_badge(booking.status))
        lines.append("")
    lines.extend(
        [
            f"Тема: {booking.topic or '—'}",
            f"Формат: {booking.format or '—'}",
            f"Длительность: {_format_duration(booking.duration_minutes)}",
            f"Дата и время: {slot_line} (MSK)",
        ]
    )
    return "\n".join(lines)


def _format_booking_list_line(booking) -> str:
    slot_line = "время пока не выбрано"
    if booking.slot_start_at and booking.slot_end_at:
        slot_line = f"{booking.slot_start_at.strftime('%d.%m %H:%M')} - {booking.slot_end_at.strftime('%H:%M')}"
    topic = booking.topic or "без темы"
    return f"{_user_status_badge(booking.status)}\n{slot_line}\nТема: {topic}"


def _format_admin_booking_card(booking, user) -> str:
    slot_text = "—"
    if booking.slot_start_at and booking.slot_end_at:
        slot_text = f"{booking.slot_start_at.strftime('%d.%m %H:%M')} - {booking.slot_end_at.strftime('%H:%M')} (MSK)"
    ttl_text = booking.expires_at.strftime('%d.%m %H:%M') if booking.expires_at else "—"
    requested_slot_text = "—"
    if booking.requested_new_slot_start_at and booking.requested_new_slot_end_at:
        requested_slot_text = (
            f"{booking.requested_new_slot_start_at.strftime('%d.%m %H:%M')} - "
            f"{booking.requested_new_slot_end_at.strftime('%H:%M')} (MSK)"
        )
    previous_slot_text = "—"
    if booking.previous_slot_start_at and booking.previous_slot_end_at:
        previous_slot_text = (
            f"{booking.previous_slot_start_at.strftime('%d.%m %H:%M')} - "
            f"{booking.previous_slot_end_at.strftime('%H:%M')} (MSK)"
        )

    return (
        "Заявка на решение администратора\n\n"
        f"ID заявки: {booking.id}\n"
        f"Пользователь: {user.name or user.telegram_display_name or '—'}\n"
        f"Username: @{user.telegram_username if user.telegram_username else 'нет'}\n"
        f"Telegram user ID: {user.telegram_user_id}\n"
        f"Тема: {booking.topic or '—'}\n"
        f"Формат: {booking.format or '—'}\n"
        f"Длительность: {booking.duration_minutes or '—'}\n"
        f"Текущий слот: {slot_text}\n"
        f"Запрошен новый слот: {requested_slot_text}\n"
        f"Предыдущий слот: {previous_slot_text}\n"
        f"Email: {user.email or '—'}\n"
        f"Комментарий: {booking.comment or '—'}\n"
        f"Статус: {booking.status}\n"
        f"TTL до: {ttl_text}"
    )


def _unique_label(label: str, existing: dict[str, str]) -> str:
    if label not in existing:
        return label
    index = 2
    while f"{label} ({index})" in existing:
        index += 1
    return f"{label} ({index})"


def _build_slot_hierarchy(slots_by_date: dict) -> dict[str, dict]:
    week_options: dict[str, str] = {}
    day_options_by_week: dict[str, dict[str, str]] = {}
    time_options_by_day: dict[str, dict[str, str]] = {}
    key_to_slot: dict[str, tuple[datetime, datetime]] = {}

    for day in sorted(slots_by_date.keys()):
        day_slots = slots_by_date[day]
        if not day_slots:
            continue

        week_start = day - timedelta(days=day.weekday())
        week_end = week_start + timedelta(days=6)
        week_key = week_start.isoformat()
        if week_key not in week_options.values():
            week_label = f"Неделя {week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')}"
            week_options[week_label] = week_key

        slots_count = len(day_slots)
        day_label = (
            f"{WEEKDAY_NAMES.get(day.weekday(), day.weekday())} "
            f"{day.strftime('%d.%m')} ({slots_count} {_slots_word(slots_count)})"
        )
        day_options_by_week.setdefault(week_key, {})
        day_options_by_week[week_key][day_label] = day.isoformat()

        day_key = day.isoformat()
        time_options_by_day.setdefault(day_key, {})
        for slot in day_slots:
            time_label = slot.start_at.strftime("%H:%M")
            time_label = _unique_label(time_label, time_options_by_day[day_key])
            slot_key = _slot_key(slot.start_at)
            time_options_by_day[day_key][time_label] = slot_key
            key_to_slot[slot_key] = (slot.start_at, slot.end_at)

    return {
        "week_options": week_options,
        "day_options_by_week": day_options_by_week,
        "time_options_by_day": time_options_by_day,
        "key_to_slot": key_to_slot,
    }


def build_booking_router(settings: Settings, session_factory: sessionmaker) -> Router:
    router = Router(name="bookings")
    logger.info("Booking router loaded: stage10")
    user_service = UserService(session_factory=session_factory)
    booking_service = BookingService(session_factory=session_factory, settings=settings)
    admin_service = AdminService(
        session_factory=session_factory,
        google_service_account_file=settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        google_calendar_id=settings.GOOGLE_CALENDAR_ID,
    )
    availability_service = AvailabilityService(session_factory=session_factory)

    async def _prompt_slot_week_step(message: Message, state: FSMContext, *, for_reschedule: bool) -> None:
        data = await state.get_data()
        week_options = data.get("slot_week_options", {})
        labels = list(week_options.keys())
        await state.update_data(slot_step="week", slot_selected_week=None, slot_selected_day=None)
        await message.answer(
            "Шаг 1/3. Выберите неделю для переноса (MSK)." if for_reschedule else "Шаг 1/3. Выберите неделю для записи (MSK).",
            reply_markup=slot_selection_keyboard(labels, columns=1),
        )

    async def _prompt_slot_day_step(message: Message, state: FSMContext, *, week_key: str, for_reschedule: bool) -> None:
        data = await state.get_data()
        day_options = data.get("slot_day_options_by_week", {}).get(week_key, {})
        labels = list(day_options.keys())
        await state.update_data(slot_step="day", slot_selected_week=week_key, slot_selected_day=None)
        await message.answer(
            "Шаг 2/3. Выберите день недели для переноса." if for_reschedule else "Шаг 2/3. Выберите день недели.",
            reply_markup=slot_selection_keyboard(labels, add_back=True, columns=1),
        )

    async def _prompt_slot_time_step(message: Message, state: FSMContext, *, day_key: str, for_reschedule: bool) -> None:
        data = await state.get_data()
        time_options = data.get("slot_time_options_by_day", {}).get(day_key, {})
        labels = list(time_options.keys())
        await state.update_data(slot_step="time", slot_selected_day=day_key)
        await message.answer(
            "Шаг 3/3. Выберите время для переноса." if for_reschedule else "Шаг 3/3. Выберите время.",
            reply_markup=slot_selection_keyboard(labels, add_back=True, columns=3),
        )

    async def _prepare_slot_selector(
        state: FSMContext,
        *,
        duration: int,
    ) -> tuple[dict[str, dict], int, int]:
        slots_by_date = availability_service.get_available_slots(duration_minutes=duration)
        hierarchy = _build_slot_hierarchy(slots_by_date)
        total_slots = len(hierarchy["key_to_slot"])
        non_empty_days = sum(1 for day_slots in slots_by_date.values() if day_slots)
        await state.update_data(
            slot_week_options=hierarchy["week_options"],
            slot_day_options_by_week=hierarchy["day_options_by_week"],
            slot_time_options_by_day=hierarchy["time_options_by_day"],
            slot_key_to_slot=hierarchy["key_to_slot"],
            slot_step="week",
            slot_selected_week=None,
            slot_selected_day=None,
        )
        return hierarchy, total_slots, non_empty_days

    async def prompt_slot_selection(message: Message, state: FSMContext) -> bool:
        data = await state.get_data()
        duration = int(data["duration_minutes"])

        _, total_slots, non_empty_days = await _prepare_slot_selector(
            state=state,
            duration=duration,
        )
        logger.info(
            "Slot selection prepared: duration=%s total_slots=%s non_empty_days=%s",
            duration,
            total_slots,
            non_empty_days,
        )

        if total_slots == 0:
            role = UserRole(data["role"])
            logger.warning(
                "No slots available for selection: duration=%s user_id=%s",
                duration,
                data.get("user_id"),
            )
            await state.clear()
            await message.answer(
                "Свободных слотов сейчас нет. Черновик сохранен, попробуйте позже.",
                reply_markup=_main_menu_for(role),
            )
            return False

        await state.set_state(BookingForm.slot_selection)
        await _prompt_slot_week_step(message, state, for_reschedule=False)
        return True

    async def notify_admin(message: Message, booking) -> None:
        if not message.from_user:
            return

        user = message.from_user
        slot_text = "—"
        if booking.slot_start_at and booking.slot_end_at:
            slot_text = f"{booking.slot_start_at.strftime('%d.%m %H:%M')} - {booking.slot_end_at.strftime('%H:%M')} (MSK)"

        text = (
            "Новая заявка на подтверждение\n\n"
            f"ID заявки: {booking.id}\n"
            f"Пользователь: {user.full_name}\n"
            f"Username: @{user.username if user.username else 'нет'}\n"
            f"Telegram user ID: {user.id}\n"
            f"Тема: {booking.topic or '—'}\n"
            f"Формат: {booking.format or '—'}\n"
            f"Длительность: {booking.duration_minutes or '—'}\n"
            f"Слот: {slot_text}\n"
            f"TTL до: {booking.expires_at.strftime('%d.%m %H:%M') if booking.expires_at else '—'}"
        )

        try:
            await message.bot.send_message(
                chat_id=settings.ADMIN_USER_ID,
                text=text,
                reply_markup=admin_booking_actions_keyboard(booking.id),
            )
            logger.info("Admin notified about booking: booking_id=%s", booking.id)
        except Exception:
            logger.exception("Failed to notify admin for booking_id=%s", booking.id)

    async def notify_user_result(
        callback: CallbackQuery,
        user_telegram_user_id: int,
        text: str,
    ) -> None:
        try:
            await callback.bot.send_message(chat_id=user_telegram_user_id, text=text)
            logger.info("User notified about decision: telegram_user_id=%s", user_telegram_user_id)
        except Exception:
            logger.exception("Failed to notify user about decision: telegram_user_id=%s", user_telegram_user_id)

    async def notify_admin_about_user_cancellation(bot, user, booking) -> None:
        text = (
            "Пользователь отменил заявку\n\n"
            f"ID заявки: {booking.id}\n"
            f"Пользователь: {user.name or user.telegram_display_name or '—'}\n"
            f"Telegram user ID: {user.telegram_user_id}\n"
            f"Тема: {booking.topic or '—'}\n"
            f"Статус: {booking.status}"
        )
        try:
            await bot.send_message(chat_id=settings.ADMIN_USER_ID, text=text)
            logger.info("Admin notified about user cancellation: booking_id=%s", booking.id)
        except Exception:
            logger.exception("Failed to notify admin about user cancellation: booking_id=%s", booking.id)

    async def notify_admin_about_reschedule_request(bot, user, booking) -> None:
        old_slot = "—"
        if booking.previous_slot_start_at and booking.previous_slot_end_at:
            old_slot = (
                f"{booking.previous_slot_start_at.strftime('%d.%m %H:%M')} - "
                f"{booking.previous_slot_end_at.strftime('%H:%M')} (MSK)"
            )
        new_slot = "—"
        if booking.requested_new_slot_start_at and booking.requested_new_slot_end_at:
            new_slot = (
                f"{booking.requested_new_slot_start_at.strftime('%d.%m %H:%M')} - "
                f"{booking.requested_new_slot_end_at.strftime('%H:%M')} (MSK)"
            )
        ttl = booking.expires_at.strftime('%d.%m %H:%M') if booking.expires_at else "—"
        text = (
            "Запрос на перенос от пользователя\n\n"
            f"ID заявки: {booking.id}\n"
            f"Пользователь: {user.name or user.telegram_display_name or '—'}\n"
            f"Telegram user ID: {user.telegram_user_id}\n"
            f"Тема: {booking.topic or '—'}\n"
            f"Старый слот: {old_slot}\n"
            f"Новый слот (запрошен): {new_slot}\n"
            f"TTL до: {ttl}"
        )
        try:
            await bot.send_message(
                chat_id=settings.ADMIN_USER_ID,
                text=text,
                reply_markup=admin_booking_actions_keyboard(booking.id),
            )
            logger.info("Admin notified about reschedule request: booking_id=%s", booking.id)
        except Exception:
            logger.exception("Failed to notify admin about reschedule request: booking_id=%s", booking.id)

    async def prompt_reschedule_slot_selection(
        message: Message,
        state: FSMContext,
        booking,
        mode: str = "reschedule",
    ) -> bool:
        duration = int(booking.duration_minutes or 0)
        if duration <= 0:
            await message.answer("У заявки не указана длительность. Перенос пока недоступен.")
            return False

        _, total_slots, _ = await _prepare_slot_selector(
            state=state,
            duration=duration,
        )
        if total_slots == 0:
            await state.clear()
            await message.answer("Свободных слотов для переноса сейчас нет. Попробуйте позже.")
            return False

        await state.update_data(
            reschedule_booking_id=booking.id,
            reschedule_duration_minutes=duration,
            reschedule_mode=mode,
        )
        await state.set_state(BookingForm.reschedule_slot_selection)
        await _prompt_slot_week_step(message, state, for_reschedule=True)
        logger.info("Reschedule flow started: booking_id=%s duration=%s", booking.id, duration)
        return True

    @router.message(Command("cancel"))
    @router.message(F.text == BTN_CANCEL)
    @router.message(F.text == "Отмена")
    async def cancel_any_step(message: Message, state: FSMContext) -> None:
        current_state = await state.get_state()
        if current_state is None:
            return

        role = user_service.resolve_role(message.from_user.id, settings.ADMIN_USER_ID) if message.from_user else UserRole.USER
        await state.clear()
        await message.answer(
            "Создание заявки отменено.",
            reply_markup=_main_menu_for(role),
        )

    @router.message(Command("new_booking"))
    @router.message(F.text == BTN_NEW_BOOKING)
    @router.message(F.text == "Новая заявка")
    async def start_new_booking(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return

        telegram_user = message.from_user
        role = user_service.resolve_role(telegram_user.id, settings.ADMIN_USER_ID)
        if user_service.is_blocked(telegram_user.id):
            await message.answer("Новые заявки для этого аккаунта недоступны.")
            return
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )

        now_msk_naive = datetime.now(MSK).replace(tzinfo=None)
        active_count = booking_service.count_future_active_for_limit(
            user_id=user.id,
            now_msk_naive=now_msk_naive,
        )
        if active_count >= 7:
            await message.answer("У вас уже 7 активных будущих заявок. Сначала завершите или отмените одну из них.")
            return

        booking = booking_service.create_draft(user_id=user.id)

        current_name = user.name or telegram_user.full_name or "Без имени"
        await state.clear()
        await state.update_data(
            booking_id=booking.id,
            user_id=user.id,
            role=role.value,
            has_username=bool(telegram_user.username),
            current_name=current_name,
            current_email=(user.email or ""),
        )
        await state.set_state(BookingForm.name)

        logger.info("Booking flow started: booking_id=%s user_id=%s", booking.id, user.id)
        await message.answer(
            f"Шаг 1/7. Имя.\nТекущее имя: {current_name}\n"
            "Отправьте новое имя или нажмите кнопку, чтобы оставить текущее.",
            reply_markup=keep_name_keyboard(current_name),
        )

    @router.message(BookingForm.name)
    async def process_name(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return

        data = await state.get_data()
        text = (message.text or "").strip()
        current_name = data.get("current_name", "")
        keep_button = f"Оставить: {current_name}"

        try:
            chosen_name = current_name if text == keep_button else validate_name(text)
        except ValueError as exc:
            await message.answer(str(exc))
            return

        user_service.update_user_profile(
            telegram_user_id=message.from_user.id,
            name=chosen_name,
        )

        await state.update_data(chosen_name=chosen_name)
        await state.set_state(BookingForm.topic)
        await message.answer(
            "Шаг 2/7. Введите тему встречи.",
            reply_markup=ReplyKeyboardRemove(),
        )

    @router.message(BookingForm.topic)
    async def process_topic(message: Message, state: FSMContext) -> None:
        data = await state.get_data()

        try:
            topic = validate_topic(message.text or "")
        except ValueError as exc:
            await message.answer(str(exc))
            return

        booking_service.update_booking_fields(
            booking_id=data["booking_id"],
            user_id=data["user_id"],
            topic=topic,
        )
        await state.set_state(BookingForm.meeting_format)
        await message.answer(
            "Шаг 3/7. Выберите формат встречи.",
            reply_markup=format_keyboard(),
        )

    @router.message(BookingForm.meeting_format)
    async def process_format(message: Message, state: FSMContext) -> None:
        data = await state.get_data()

        try:
            meeting_format = validate_meeting_format(message.text or "")
        except ValueError as exc:
            await message.answer(str(exc))
            return

        booking_service.update_booking_fields(
            booking_id=data["booking_id"],
            user_id=data["user_id"],
            format=meeting_format,
        )
        await state.set_state(BookingForm.duration)
        await message.answer(
            "Шаг 4/7. Выберите длительность.",
            reply_markup=duration_keyboard(),
        )

    @router.message(BookingForm.duration)
    async def process_duration(message: Message, state: FSMContext) -> None:
        data = await state.get_data()

        try:
            duration = validate_duration(message.text or "")
        except ValueError as exc:
            await message.answer(str(exc))
            return

        booking_service.update_booking_fields(
            booking_id=data["booking_id"],
            user_id=data["user_id"],
            duration_minutes=duration,
        )
        await state.update_data(duration_minutes=duration)
        await state.set_state(BookingForm.email)
        current_email = str(data.get("current_email") or "").strip()
        if current_email:
            await message.answer(
                f"Шаг 5/7. Укажите e-mail или нажмите кнопку, чтобы оставить текущий.\n"
                f"Текущий e-mail: {current_email}",
                reply_markup=keep_email_keyboard(current_email),
            )
        else:
            await message.answer(
                "Шаг 5/7. Укажите e-mail или нажмите «⏭ Пропустить».",
                reply_markup=optional_skip_keyboard(),
            )

    @router.message(BookingForm.email)
    async def process_email(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return

        data = await state.get_data()
        text = (message.text or "").strip()
        current_email = str(data.get("current_email") or "").strip()
        keep_button = f"Оставить: {current_email}" if current_email else ""

        try:
            if keep_button and text == keep_button:
                email = current_email
            else:
                email = None if _is_skip_text(text) else parse_optional_email(text)
        except ValueError as exc:
            await message.answer(str(exc))
            return

        user_service.update_user_profile(
            telegram_user_id=message.from_user.id,
            email=email,
        )

        has_username = bool(data.get("has_username"))
        if requires_alternative_contact(has_username=has_username, email=email):
            await state.set_state(BookingForm.phone_if_needed)
            await message.answer(
                "У вас нет username, поэтому нужен альтернативный контакт.\n"
                "Введите номер телефона.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        await state.set_state(BookingForm.comment)
        await message.answer(
            "Шаг 6/7. Комментарий (необязательно) или «⏭ Пропустить».",
            reply_markup=optional_skip_keyboard(),
        )

    @router.message(BookingForm.phone_if_needed)
    async def process_phone_if_needed(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return

        try:
            phone = validate_phone(message.text or "")
        except ValueError as exc:
            await message.answer(str(exc))
            return

        user_service.update_user_profile(
            telegram_user_id=message.from_user.id,
            phone=phone,
        )
        await state.set_state(BookingForm.comment)
        await message.answer(
            "Шаг 6/7. Комментарий (необязательно) или «⏭ Пропустить».",
            reply_markup=optional_skip_keyboard(),
        )

    @router.message(BookingForm.comment)
    async def process_comment(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        text = (message.text or "").strip()
        comment = None if _is_skip_text(text) else parse_optional_comment(text)

        booking_service.update_booking_fields(
            booking_id=data["booking_id"],
            user_id=data["user_id"],
            comment=comment,
            status="draft",
        )

        await message.answer(
            "Шаг 7/7. Подбираю доступные слоты...",
            reply_markup=ReplyKeyboardRemove(),
        )
        await prompt_slot_selection(message, state)

    @router.message(BookingForm.slot_selection)
    async def process_slot_selection(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return

        text = (message.text or "").strip()
        if _is_admin_settings_text(text):
            await state.clear()
            await admin_settings_menu(message)
            return
        if _is_admin_bookings_text(text):
            await state.clear()
            await show_admin_bookings(message)
            return
        if text.startswith("/admin_"):
            await state.clear()
            await message.answer("Режим выбора слота закрыт. Повторите админ-команду ещё раз.")
            return
        if _is_my_bookings_text(text):
            await state.clear()
            await show_my_bookings(message)
            return
        if _is_new_booking_text(text):
            await state.clear()
            await start_new_booking(message, state)
            return
        if _is_refresh_slots_text(text):
            await prompt_slot_selection(message, state)
            return

        data = await state.get_data()
        step = str(data.get("slot_step") or "week")
        selected_week = data.get("slot_selected_week")
        selected_day = data.get("slot_selected_day")

        if _is_back_text(text):
            if step == "day":
                await _prompt_slot_week_step(message, state, for_reschedule=False)
                return
            if step == "time" and selected_week:
                await _prompt_slot_day_step(message, state, week_key=selected_week, for_reschedule=False)
                return
            await _prompt_slot_week_step(message, state, for_reschedule=False)
            return

        duration = int(data["duration_minutes"])
        week_options = data.get("slot_week_options", {})
        day_options_by_week = data.get("slot_day_options_by_week", {})
        time_options_by_day = data.get("slot_time_options_by_day", {})

        if step == "week":
            if text not in week_options:
                await message.answer("Выберите неделю кнопкой из списка.")
                return
            await _prompt_slot_day_step(
                message,
                state,
                week_key=week_options[text],
                for_reschedule=False,
            )
            return

        if step == "day":
            if not selected_week:
                await _prompt_slot_week_step(message, state, for_reschedule=False)
                return
            day_options = day_options_by_week.get(selected_week, {})
            if text not in day_options:
                await message.answer("Выберите день кнопкой из списка.")
                return
            await _prompt_slot_time_step(
                message,
                state,
                day_key=day_options[text],
                for_reschedule=False,
            )
            return

        if step != "time" or not selected_day:
            await _prompt_slot_week_step(message, state, for_reschedule=False)
            return

        time_options = time_options_by_day.get(selected_day, {})
        if text not in time_options:
            await message.answer("Выберите время кнопкой из списка.")
            return

        selected_key = time_options[text]
        live_slots = availability_service.get_available_slots(duration_minutes=duration)
        live_key_to_slot = _build_slot_hierarchy(live_slots)["key_to_slot"]

        if selected_key not in live_key_to_slot:
            await message.answer("Этот слот уже недоступен. Обновляю недели и слоты...")
            await prompt_slot_selection(message, state)
            return

        selected_start_at, selected_end_at = live_key_to_slot[selected_key]
        now_msk = datetime.now(MSK)
        expires_at = (now_msk + timedelta(hours=72)).replace(tzinfo=None)

        try:
            booking = booking_service.hold_slot_and_submit(
                booking_id=data["booking_id"],
                user_id=data["user_id"],
                slot_start_at_msk_naive=selected_start_at.replace(tzinfo=None),
                slot_end_at_msk_naive=selected_end_at.replace(tzinfo=None),
                expires_at_msk_naive=expires_at,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            await prompt_slot_selection(message, state)
            return

        await notify_admin(message, booking)

        role = UserRole(data["role"])
        await state.clear()
        await message.answer(
            "🟡 Заявка отправлена на подтверждение.\n"
            "Мы сообщим, как только администратор примет решение.\n\n"
            + _format_booking_card_line(booking, include_status_badge=False),
            reply_markup=_main_menu_for(role),
        )

    @router.message(Command("my_bookings"))
    @router.message(F.text == BTN_MY_BOOKINGS)
    @router.message(F.text == "Мои заявки")
    async def show_my_bookings(message: Message) -> None:
        if not message.from_user:
            return

        telegram_user = message.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )

        bookings = booking_service.list_active_bookings(user_id=user.id)
        if not bookings:
            await message.answer("У вас пока нет активных заявок.")
            return

        logger.info(
            "User bookings list opened: user_id=%s telegram_user_id=%s count=%s",
            user.id,
            telegram_user.id,
            len(bookings),
        )
        await message.answer(f"📂 Активных заявок: {len(bookings)}")
        for booking in bookings:
            await message.answer(
                _format_booking_list_line(booking),
                reply_markup=user_booking_open_keyboard(booking.id),
            )

    @router.callback_query(F.data.startswith("user:open:"))
    async def user_open_booking_card(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        telegram_user = callback.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )
        try:
            booking = booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        logger.info("Booking card opened by user: booking_id=%s user_id=%s", booking.id, user.id)
        if callback.message:
            await callback.message.answer(
                _format_booking_card_line(booking),
                reply_markup=user_booking_actions_keyboard(booking.id),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("user:cancel:"))
    async def user_cancel_booking(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        telegram_user = callback.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )
        try:
            booking = booking_service.cancel_booking_by_user(
                booking_id=booking_id,
                user_id=user.id,
                user_telegram_user_id=telegram_user.id,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        except Exception:
            logger.exception("User cancel failed: booking_id=%s user_id=%s", booking_id, user.id)
            await callback.answer("Ошибка при отмене заявки.", show_alert=True)
            return

        logger.info("Booking canceled by user via callback: booking_id=%s user_id=%s", booking.id, user.id)
        if callback.message:
            await callback.message.answer(
                "🚫 Заявка отменена.\n\n" + _format_booking_card_line(booking, include_status_badge=False),
                reply_markup=None,
            )
        await notify_admin_about_user_cancellation(callback.bot, user, booking)
        await callback.answer("Отменено.")

    @router.callback_query(F.data.startswith("user:reschedule:"))
    async def user_start_reschedule(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            return
        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        telegram_user = callback.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )
        try:
            booking = booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        if booking.status not in {"pending_decision", "confirmed"}:
            await callback.answer("Перенос доступен только для ожидающих и подтвержденных заявок.", show_alert=True)
            return
        if callback.message:
            await callback.message.answer("Подбираю слоты для переноса...")
            await prompt_reschedule_slot_selection(callback.message, state, booking)
        await callback.answer()

    @router.callback_query(F.data.startswith("user:waitlist_accept:"))
    async def user_accept_waitlist_offer(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        telegram_user = callback.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )
        try:
            booking = booking_service.accept_waitlist_offer_by_user(
                booking_id=booking_id,
                user_id=user.id,
                user_telegram_user_id=telegram_user.id,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        if callback.message:
            await callback.message.answer(
                "✅ Слот принят. Заявка подтверждена.\n\n"
                + _format_booking_card_line(booking, include_status_badge=False)
            )
        try:
            username_line = (
                f"Telegram: @{user.telegram_username}"
                if user.telegram_username
                else "Telegram: не указан"
            )
            await callback.bot.send_message(
                chat_id=settings.ADMIN_USER_ID,
                text=(
                    "✅ Клиент принял предложенный слот.\n\n"
                    f"Заявка ID: {booking.id}\n"
                    f"Пользователь: {user.name or user.telegram_display_name or '—'}\n"
                    f"{username_line}"
                ),
            )
        except Exception:
            logger.exception("Failed to notify admin after waitlist accept: booking_id=%s", booking.id)
        await callback.answer("Слот принят.")

    @router.callback_query(F.data.startswith("user:waitlist_reject:"))
    async def user_reject_waitlist_offer(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        telegram_user = callback.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )
        try:
            booking = booking_service.reject_waitlist_offer_by_user(
                booking_id=booking_id,
                user_id=user.id,
                user_telegram_user_id=telegram_user.id,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        if callback.message:
            await callback.message.answer(
                "❌ Предложенный слот отклонён. Заявка возвращена в лист ожидания.\n\n"
                + _format_booking_card_line(booking, include_status_badge=False),
            )
        try:
            username_line = (
                f"Telegram: @{user.telegram_username}"
                if user.telegram_username
                else "Telegram: не указан"
            )
            await callback.bot.send_message(
                chat_id=settings.ADMIN_USER_ID,
                text=(
                    "❌ Клиент отклонил предложенный слот.\n\n"
                    f"Заявка ID: {booking.id}\n"
                    f"Пользователь: {user.name or user.telegram_display_name or '—'}\n"
                    f"{username_line}"
                ),
            )
        except Exception:
            logger.exception("Failed to notify admin after waitlist reject: booking_id=%s", booking.id)
        await callback.answer("Слот отклонён.")

    @router.message(BookingForm.reschedule_slot_selection)
    async def process_reschedule_slot_selection(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return

        text = (message.text or "").strip()
        if _is_admin_settings_text(text):
            await state.clear()
            await admin_settings_menu(message)
            return
        if _is_admin_bookings_text(text):
            await state.clear()
            await show_admin_bookings(message)
            return
        if text.startswith("/admin_"):
            await state.clear()
            await message.answer("Режим переноса закрыт. Повторите админ-команду ещё раз.")
            return
        if _is_my_bookings_text(text):
            await state.clear()
            await show_my_bookings(message)
            return
        if _is_new_booking_text(text):
            await state.clear()
            await start_new_booking(message, state)
            return
        data = await state.get_data()
        booking_id = data.get("reschedule_booking_id")
        duration = int(data.get("reschedule_duration_minutes") or 0)
        mode = str(data.get("reschedule_mode") or "reschedule")
        if booking_id is None or duration <= 0:
            await state.clear()
            await message.answer("Сценарий переноса сброшен. Начните заново через 'Мои заявки'.")
            return

        if _is_refresh_slots_text(text):
            telegram_user = message.from_user
            user = user_service.ensure_user_from_telegram(
                telegram_user_id=telegram_user.id,
                telegram_username=telegram_user.username,
                telegram_display_name=telegram_user.full_name,
            )
            try:
                booking = booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
            except ValueError as exc:
                await state.clear()
                await message.answer(str(exc))
                return
            await prompt_reschedule_slot_selection(message, state, booking, mode=mode)
            return

        step = str(data.get("slot_step") or "week")
        selected_week = data.get("slot_selected_week")
        selected_day = data.get("slot_selected_day")
        week_options = data.get("slot_week_options", {})
        day_options_by_week = data.get("slot_day_options_by_week", {})
        time_options_by_day = data.get("slot_time_options_by_day", {})

        if _is_back_text(text):
            if step == "day":
                await _prompt_slot_week_step(message, state, for_reschedule=True)
                return
            if step == "time" and selected_week:
                await _prompt_slot_day_step(message, state, week_key=selected_week, for_reschedule=True)
                return
            await _prompt_slot_week_step(message, state, for_reschedule=True)
            return

        if step == "week":
            if text not in week_options:
                await message.answer("Выберите неделю кнопкой из списка.")
                return
            await _prompt_slot_day_step(
                message,
                state,
                week_key=week_options[text],
                for_reschedule=True,
            )
            return

        if step == "day":
            if not selected_week:
                await _prompt_slot_week_step(message, state, for_reschedule=True)
                return
            day_options = day_options_by_week.get(selected_week, {})
            if text not in day_options:
                await message.answer("Выберите день кнопкой из списка.")
                return
            await _prompt_slot_time_step(
                message,
                state,
                day_key=day_options[text],
                for_reschedule=True,
            )
            return

        if step != "time" or not selected_day:
            await _prompt_slot_week_step(message, state, for_reschedule=True)
            return

        time_options = time_options_by_day.get(selected_day, {})
        if text not in time_options:
            await message.answer("Выберите время кнопкой из списка.")
            return

        selected_key = time_options[text]
        live_slots = availability_service.get_available_slots(duration_minutes=duration)
        live_key_to_slot = _build_slot_hierarchy(live_slots)["key_to_slot"]
        if selected_key not in live_key_to_slot:
            await message.answer("Этот слот уже недоступен. Обновляю недели и слоты...")
            telegram_user = message.from_user
            user = user_service.ensure_user_from_telegram(
                telegram_user_id=telegram_user.id,
                telegram_username=telegram_user.username,
                telegram_display_name=telegram_user.full_name,
            )
            try:
                booking = booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
            except ValueError as exc:
                await state.clear()
                await message.answer(str(exc))
                return
            await prompt_reschedule_slot_selection(message, state, booking, mode=mode)
            return

        selected_start_at, selected_end_at = live_key_to_slot[selected_key]
        expires_at = (datetime.now(MSK) + timedelta(hours=72)).replace(tzinfo=None)
        telegram_user = message.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )
        try:
            if mode == "choose_other_time":
                booking = booking_service.rebook_after_closed_day_by_user(
                    booking_id=booking_id,
                    user_id=user.id,
                    user_telegram_user_id=telegram_user.id,
                    slot_start_at_msk_naive=selected_start_at.replace(tzinfo=None),
                    slot_end_at_msk_naive=selected_end_at.replace(tzinfo=None),
                    expires_at_msk_naive=expires_at,
                )
            else:
                booking = booking_service.request_reschedule_by_user(
                    booking_id=booking_id,
                    user_id=user.id,
                    user_telegram_user_id=telegram_user.id,
                    requested_start_at_msk_naive=selected_start_at.replace(tzinfo=None),
                    requested_end_at_msk_naive=selected_end_at.replace(tzinfo=None),
                    expires_at_msk_naive=expires_at,
                )
        except ValueError as exc:
            await message.answer(str(exc))
            try:
                booking_fresh = booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
            except ValueError:
                await state.clear()
                return
            await prompt_reschedule_slot_selection(message, state, booking_fresh, mode=mode)
            return

        if mode == "choose_other_time":
            await notify_admin(message, booking)
        else:
            await notify_admin_about_reschedule_request(message.bot, user, booking)
        await state.clear()
        await message.answer(
            (
                "Заявка повторно отправлена администратору с новым слотом.\n\n"
                if mode == "choose_other_time"
                else "Запрос на перенос отправлен администратору.\n"
                "Новый слот временно удержан, старый слот сохранен до решения.\n\n"
            )
            + _format_booking_card_line(booking),
            reply_markup=_main_menu_for(user_service.resolve_role(telegram_user.id, settings.ADMIN_USER_ID)),
        )

    @router.callback_query(F.data.startswith("user:choose_other_time:"))
    async def user_choose_other_time(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            return
        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[3])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return
        telegram_user = callback.from_user
        user = user_service.ensure_user_from_telegram(
            telegram_user_id=telegram_user.id,
            telegram_username=telegram_user.username,
            telegram_display_name=telegram_user.full_name,
        )
        try:
            booking = booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if booking.status != "canceled_by_admin":
            await callback.answer("Эта заявка не доступна для повторного выбора времени.", show_alert=True)
            return
        if callback.message:
            await callback.message.answer("Подбираю новые слоты...")
            await prompt_reschedule_slot_selection(callback.message, state, booking, mode="choose_other_time")
        await callback.answer()

    async def _ensure_admin_access(message: Message) -> bool:
        if not message.from_user:
            return False
        role = user_service.resolve_role(message.from_user.id, settings.ADMIN_USER_ID)
        if role != UserRole.ADMIN:
            await message.answer("Доступно только администратору.")
            return False
        return True

    async def _maybe_exit_admin_state(message: Message, state: FSMContext) -> bool:
        text = (message.text or "").strip()
        lowered = text.lower()
        if text in {BTN_BACK_SETTINGS, "Назад в настройки"} or _is_cancel_text(text):
            await state.clear()
            await admin_settings_menu(message, state)
            return True
        if text == BTN_BACK_WINDOWS:
            await state.clear()
            await admin_windows_menu(message, state)
            return True
        if text in {BTN_BACK_ADMIN, "Назад в админ-меню"}:
            await state.clear()
            await message.answer("Возвращаю в админ-меню.", reply_markup=admin_main_keyboard())
            return True
        if lowered in {"старт", "start"} or text == "/start":
            await state.clear()
            await message.answer("Возвращаю в главное меню администратора.", reply_markup=admin_main_keyboard())
            return True
        return False

    async def _execute_close_day(message: Message, target_date: dt_date, reason: str | None = None) -> None:
        canceled = admin_service.close_day(target_date=target_date, reason=reason)
        for item in canceled:
            try:
                await message.bot.send_message(
                    chat_id=item.user_telegram_user_id,
                    text=(
                        "🚫 Встреча отменена: этот день закрыт администратором.\n"
                        "Нажмите кнопку ниже, чтобы выбрать другое время."
                    ),
                    reply_markup=choose_other_time_keyboard(item.booking_id),
                )
            except Exception:
                logger.exception("Failed to notify user after closed date: booking_id=%s", item.booking_id)
        await message.answer(f"Дата закрыта: {target_date.isoformat()}. Отменено заявок: {len(canceled)}")

    async def _show_closed_days_list(message: Message) -> None:
        rows = admin_service.list_closed_days(limit=180)
        if not rows:
            await message.answer("Список закрытых дней пуст.")
            return
        lines = ["Закрытые дни:"]
        for row in rows[:50]:
            reason = f" | причина: {row.reason}" if row.reason else ""
            lines.append(f"- {row.date.isoformat()}{reason}")
        await message.answer("\n".join(lines))

    async def _prompt_reopen_day_week_step(message: Message, state: FSMContext) -> None:
        week_options = _build_future_week_options()
        await state.update_data(
            admin_reopen_day_step="week",
            admin_reopen_day_week_options=week_options,
            admin_reopen_day_day_options={},
        )
        await message.answer(
            "Открыть день: шаг 1/2. Выберите неделю.",
            reply_markup=slot_selection_keyboard(list(week_options.keys()), add_back=True, columns=1),
        )

    async def _prompt_reopen_day_day_step(message: Message, state: FSMContext, week_start: dt_date) -> None:
        day_options = _build_week_days_options(week_start)
        await state.update_data(
            admin_reopen_day_step="day",
            admin_reopen_day_day_options=day_options,
        )
        await message.answer(
            "Открыть день: шаг 2/2. Выберите день.",
            reply_markup=slot_selection_keyboard(list(day_options.keys()), add_back=True, columns=1),
        )

    async def _show_one_time_windows_list(message: Message) -> None:
        rows = admin_service.list_one_time_windows(limit=180)
        if not rows:
            await message.answer("Список разовых окон пуст.")
            return
        lines = ["Разовые окна:"]
        for row in rows[:60]:
            comment = f" | {row.get('comment')}" if row.get("comment") else ""
            lines.append(f"- {row.get('date')} {row.get('start')}-{row.get('end')}{comment}")
        await message.answer("\n".join(lines))

    async def _prompt_close_day_week_step(message: Message, state: FSMContext) -> None:
        week_options = _build_future_week_options()
        await state.update_data(
            admin_close_day_mode="picker",
            admin_close_day_step="week",
            admin_close_day_week_options=week_options,
            admin_close_day_day_options={},
        )
        await message.answer(
            "Закрыть день: шаг 1/2. Выберите неделю.",
            reply_markup=slot_selection_keyboard(list(week_options.keys()), add_back=True, columns=1),
        )

    async def _prompt_close_day_day_step(message: Message, state: FSMContext, week_start: dt_date) -> None:
        day_options = _build_week_days_options(week_start)
        await state.update_data(admin_close_day_step="day", admin_close_day_day_options=day_options)
        await message.answer(
            "Закрыть день: шаг 2/2. Выберите день.",
            reply_markup=slot_selection_keyboard(list(day_options.keys()), add_back=True, columns=1),
        )

    @router.message(Command("admin_settings"))
    @router.message(F.text == BTN_ADMIN_SETTINGS)
    @router.message(F.text == "Админ: настройки")
    async def admin_settings_menu(message: Message, state: FSMContext | None = None) -> None:
        if not await _ensure_admin_access(message):
            return
        if state is not None:
            await state.clear()
        await message.answer(
            "Настройки администратора.\nВыберите действие кнопкой:",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(F.text == BTN_BACK_ADMIN)
    @router.message(F.text == BTN_BACK_SETTINGS)
    @router.message(F.text == "Назад в админ-меню")
    @router.message(F.text == "Назад в настройки")
    async def admin_settings_back(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.clear()
        text = (message.text or "").strip()
        if text in {BTN_BACK_ADMIN, "Назад в админ-меню"}:
            await message.answer("Возвращаю в админ-меню.", reply_markup=admin_main_keyboard())
            return
        await message.answer("Возвращаю в настройки.", reply_markup=admin_settings_keyboard())

    @router.message(F.text == BTN_WINDOWS)
    @router.message(F.text == "Окна работы")
    async def admin_windows_menu(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.clear()
        await message.answer(
            "Управление окнами работы.\n"
            "Важно: окна работы — это шаблон по дням недели (Пн–Вс), он действует для всех недель.\n"
            "Для разового закрытия конкретной даты используйте «Закрыть день» или «Добавить блок».\n"
            "Выберите действие. День недели можно выбрать кнопками.",
            reply_markup=admin_windows_keyboard(),
        )

    @router.message(F.text == BTN_CLOSE_DAY)
    @router.message(F.text == "Закрыть день")
    async def admin_settings_close_day_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_close_date)
        await state.update_data(admin_close_day_mode=None, admin_close_day_step=None)
        await message.answer(
            "Закрытие дня:\n"
            "1) можно выбрать дату кнопками,\n"
            "2) или ввести вручную в формате YYYY-MM-DD [причина].",
            reply_markup=admin_manual_or_picker_keyboard(),
        )

    @router.message(F.text == BTN_LIST_CLOSED_DAYS)
    async def admin_settings_list_closed_days(message: Message) -> None:
        if not await _ensure_admin_access(message):
            return
        await _show_closed_days_list(message)

    @router.message(F.text == BTN_REOPEN_DAY)
    async def admin_settings_reopen_day_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_reopen_day)
        await _prompt_reopen_day_week_step(message, state)

    @router.message(BookingForm.admin_reopen_day)
    async def admin_settings_reopen_day_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        if await _maybe_exit_admin_state(message, state):
            return
        text = (message.text or "").strip()
        data = await state.get_data()
        step = data.get("admin_reopen_day_step")

        if _is_back_text(text):
            if step == "day":
                await _prompt_reopen_day_week_step(message, state)
                return
            await state.clear()
            await message.answer("Возвращаю в настройки.", reply_markup=admin_settings_keyboard())
            return

        if step == "week":
            week_options = data.get("admin_reopen_day_week_options", {})
            if text not in week_options:
                await message.answer("Выберите неделю кнопкой из списка.")
                return
            week_start = _parse_date(week_options[text])
            await _prompt_reopen_day_day_step(message, state, week_start=week_start)
            return

        if step != "day":
            await _prompt_reopen_day_week_step(message, state)
            return

        day_options = data.get("admin_reopen_day_day_options", {})
        if text not in day_options:
            await message.answer("Выберите день кнопкой из списка.")
            return
        target_date = _parse_date(day_options[text])
        reopened = admin_service.reopen_day(target_date=target_date)
        await state.clear()
        await message.answer(
            ("День открыт." if reopened else "Эта дата не была закрыта."),
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(BookingForm.admin_close_date)
    async def admin_settings_close_day_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        if await _maybe_exit_admin_state(message, state):
            return
        text = (message.text or "").strip()
        data = await state.get_data()
        mode = data.get("admin_close_day_mode")
        step = data.get("admin_close_day_step")

        if text == BTN_PICK_FROM_LIST:
            await _prompt_close_day_week_step(message, state)
            return
        if text == BTN_MANUAL_INPUT:
            await state.update_data(admin_close_day_mode="manual", admin_close_day_step="manual")
            await message.answer(
                "Введите дату вручную: YYYY-MM-DD [причина]\nПример: 2026-05-12 Отпуск",
                reply_markup=admin_manual_entry_keyboard(),
            )
            return

        if _is_back_text(text) and mode == "picker":
            if step == "day":
                await _prompt_close_day_week_step(message, state)
            else:
                await message.answer(
                    "Выберите способ: кнопками или вручную.",
                    reply_markup=admin_manual_or_picker_keyboard(),
                )
            return

        if mode == "picker":
            if step == "week":
                week_options = data.get("admin_close_day_week_options", {})
                if text not in week_options:
                    await message.answer("Выберите неделю кнопкой из списка.")
                    return
                week_start = _parse_date(week_options[text])
                await _prompt_close_day_day_step(message, state, week_start=week_start)
                return
            if step == "day":
                day_options = data.get("admin_close_day_day_options", {})
                if text not in day_options:
                    await message.answer("Выберите день кнопкой из списка.")
                    return
                target_date = _parse_date(day_options[text])
                try:
                    await _execute_close_day(message, target_date=target_date, reason=None)
                except Exception as exc:
                    await message.answer(f"Ошибка: {exc}")
                    return
                await state.clear()
                await message.answer("Настройки обновлены.", reply_markup=admin_settings_keyboard())
                return

        if mode != "manual":
            await message.answer(
                "Выберите способ: кнопками или вручную.",
                reply_markup=admin_manual_or_picker_keyboard(),
            )
            return

        parts = text.split(maxsplit=1)
        if not parts:
            await message.answer("Формат: YYYY-MM-DD [причина]")
            return
        try:
            target_date = _parse_date(parts[0])
            reason = parts[1] if len(parts) > 1 else None
            await _execute_close_day(message, target_date=target_date, reason=reason)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer("Настройки обновлены.", reply_markup=admin_settings_keyboard())

    @router.message(F.text == BTN_ADD_BLOCK)
    @router.message(F.text == "Добавить блок")
    async def admin_settings_add_block_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_add_block)
        await message.answer(
            "Введите блок в формате:\nYYYY-MM-DD HH:MM HH:MM [комментарий]\n"
            "Пример: 2026-05-15 13:00 14:00 Внутренняя встреча",
            reply_markup=admin_manual_entry_keyboard(),
        )

    @router.message(BookingForm.admin_add_block)
    async def admin_settings_add_block_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        if await _maybe_exit_admin_state(message, state):
            return
        parts = (message.text or "").split(maxsplit=3)
        if len(parts) < 3:
            await message.answer("Формат: YYYY-MM-DD HH:MM HH:MM [комментарий]")
            return
        try:
            target_date = _parse_date(parts[0])
            start_at = _parse_time(parts[1])
            end_at = _parse_time(parts[2])
            comment = parts[3] if len(parts) > 3 else None
            block = admin_service.add_time_block(
                target_date=target_date,
                start_at=start_at,
                end_at=end_at,
                comment=comment,
            )
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer(
            f"Блок создан: id={block.id} {target_date.isoformat()} {start_at.strftime('%H:%M')}-{end_at.strftime('%H:%M')}",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(F.text == BTN_MIN_LEAD)
    @router.message(F.text == "Мин. срок подачи")
    async def admin_settings_min_lead_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_set_min_lead)
        current = admin_service.get_min_lead_minutes()
        await message.answer(
            "Введите минимальный срок подачи в минутах (0..10080).\n"
            f"Текущее значение: {current if current is not None else 'не задано'}",
            reply_markup=admin_manual_entry_keyboard(),
        )

    @router.message(BookingForm.admin_set_min_lead)
    async def admin_settings_min_lead_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        if await _maybe_exit_admin_state(message, state):
            return
        raw = (message.text or "").strip()
        try:
            minutes = int(raw)
            admin_service.set_min_lead_minutes(minutes)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer(
            f"Минимальный срок подачи заявки обновлен: {minutes} минут.",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(F.text == BTN_ADD_WINDOW)
    @router.message(F.text == "Добавить окно работы")
    async def admin_settings_set_window_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_set_window)
        await state.update_data(admin_set_window_step="weekday", admin_set_window_weekday=None)
        await message.answer(
            "Добавить окно работы (шаблон для всех недель): выберите день недели.",
            reply_markup=admin_weekday_keyboard(back_to_windows=True),
        )

    @router.message(BookingForm.admin_set_window)
    async def admin_settings_set_window_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        text = (message.text or "").strip()
        if text == BTN_BACK_WINDOWS:
            await state.clear()
            await admin_windows_menu(message, state)
            return
        if await _maybe_exit_admin_state(message, state):
            return
        data = await state.get_data()
        step = data.get("admin_set_window_step")

        if step == "weekday":
            weekday = WEEKDAY_LABEL_TO_INDEX.get(text)
            if weekday is None:
                await message.answer("Выберите день недели кнопкой.")
                return
            await state.update_data(admin_set_window_step="interval", admin_set_window_weekday=weekday)
            await message.answer(
                f"День выбран: {WEEKDAY_NAMES.get(weekday, weekday)}.\n"
                "Теперь введите интервал времени (он будет применяться к каждой такой дате): HH:MM HH:MM\n"
                "Пример: 10:00 18:00",
                reply_markup=admin_manual_entry_keyboard(back_to_windows=True),
            )
            return

        weekday = data.get("admin_set_window_weekday")
        parts = text.split()
        if weekday is None or len(parts) != 2:
            await message.answer("Формат интервала: HH:MM HH:MM")
            return
        try:
            start_at = _parse_time(parts[0])
            end_at = _parse_time(parts[1])
            rule = admin_service.set_working_window(weekday=weekday, start_at=start_at, end_at=end_at)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer(
            f"Окно добавлено: rule_id={rule.id}, день={WEEKDAY_NAMES.get(weekday, weekday)}, {parts[0]}-{parts[1]}",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(F.text == BTN_CLEAR_WINDOWS)
    @router.message(F.text == "Очистить окна работы")
    async def admin_settings_clear_windows_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_clear_windows)
        await state.update_data(admin_clear_windows_step="pick")
        await message.answer(
            "Очистить окна (в недельном шаблоне): выберите день недели или «Очистить все окна».",
            reply_markup=admin_weekday_keyboard(include_clear_all=True, back_to_windows=True),
        )

    @router.message(BookingForm.admin_clear_windows)
    async def admin_settings_clear_windows_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        text = (message.text or "").strip()
        if text == BTN_BACK_WINDOWS:
            await state.clear()
            await admin_windows_menu(message, state)
            return
        if await _maybe_exit_admin_state(message, state):
            return
        try:
            if text == BTN_CLEAR_WINDOWS_ALL:
                weekday = None
            else:
                weekday = WEEKDAY_LABEL_TO_INDEX.get(text)
                if weekday is None:
                    await message.answer("Выберите день кнопкой или «Очистить все окна».")
                    return
            deleted = admin_service.clear_working_windows(weekday=weekday)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer(
            f"Удалено окон: {deleted}",
            reply_markup=admin_settings_keyboard(),
        )

    async def _prompt_one_time_window_week_step(message: Message, state: FSMContext) -> None:
        week_options = _build_future_week_options()
        await state.update_data(
            admin_one_time_window_step="week",
            admin_one_time_window_week_options=week_options,
            admin_one_time_window_day_options={},
            admin_one_time_window_date=None,
        )
        await message.answer(
            "Разовое окно: шаг 1/3. Выберите неделю.",
            reply_markup=slot_selection_keyboard(list(week_options.keys()), add_back=True, columns=1),
        )

    async def _prompt_one_time_window_day_step(message: Message, state: FSMContext, week_start: dt_date) -> None:
        day_options = _build_week_days_options(week_start)
        await state.update_data(
            admin_one_time_window_step="day",
            admin_one_time_window_day_options=day_options,
            admin_one_time_window_date=None,
        )
        await message.answer(
            "Разовое окно: шаг 2/3. Выберите конкретный день.",
            reply_markup=slot_selection_keyboard(list(day_options.keys()), add_back=True, columns=1),
        )

    @router.message(F.text == BTN_ONE_TIME_WINDOW)
    async def admin_settings_one_time_window_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_one_time_window)
        await _prompt_one_time_window_week_step(message, state)

    @router.message(F.text == BTN_LIST_ONE_TIME_WINDOWS)
    async def admin_settings_list_one_time_windows(message: Message) -> None:
        if not await _ensure_admin_access(message):
            return
        await _show_one_time_windows_list(message)

    @router.message(BookingForm.admin_one_time_window)
    async def admin_settings_one_time_window_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        text = (message.text or "").strip()
        if text == BTN_BACK_WINDOWS:
            await state.clear()
            await admin_windows_menu(message, state)
            return
        if await _maybe_exit_admin_state(message, state):
            return

        data = await state.get_data()
        step = data.get("admin_one_time_window_step")

        if _is_back_text(text):
            if step == "day":
                await _prompt_one_time_window_week_step(message, state)
                return
            if step == "interval":
                week_start_raw = data.get("admin_one_time_window_week_start")
                if week_start_raw:
                    await _prompt_one_time_window_day_step(message, state, _parse_date(week_start_raw))
                    return
                await _prompt_one_time_window_week_step(message, state)
                return
            await admin_windows_menu(message, state)
            return

        if step == "week":
            week_options = data.get("admin_one_time_window_week_options", {})
            if text not in week_options:
                await message.answer("Выберите неделю кнопкой из списка.")
                return
            week_start_raw = week_options[text]
            await state.update_data(admin_one_time_window_week_start=week_start_raw)
            await _prompt_one_time_window_day_step(message, state, _parse_date(week_start_raw))
            return

        if step == "day":
            day_options = data.get("admin_one_time_window_day_options", {})
            if text not in day_options:
                await message.answer("Выберите день кнопкой из списка.")
                return
            selected_date_raw = day_options[text]
            selected_date = _parse_date(selected_date_raw)
            await state.update_data(
                admin_one_time_window_step="interval",
                admin_one_time_window_date=selected_date_raw,
            )
            await message.answer(
                f"Разовое окно: шаг 3/3.\n"
                f"Дата: {selected_date.strftime('%d.%m.%Y')} ({WEEKDAY_NAMES.get(selected_date.weekday(), selected_date.weekday())}).\n"
                "Введите интервал: HH:MM HH:MM\n"
                "Пример: 17:00 19:00",
                reply_markup=admin_manual_entry_keyboard(back_to_windows=True),
            )
            return

        selected_date_raw = data.get("admin_one_time_window_date")
        parts = text.split(maxsplit=2)
        if not selected_date_raw or len(parts) < 2:
            await message.answer("Формат: HH:MM HH:MM [комментарий]")
            return
        try:
            target_date = _parse_date(selected_date_raw)
            start_at = _parse_time(parts[0])
            end_at = _parse_time(parts[1])
            comment = parts[2] if len(parts) > 2 else None
            item = admin_service.add_one_time_window(
                target_date=target_date,
                start_at=start_at,
                end_at=end_at,
                comment=comment,
            )
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer(
            f"Разовое окно добавлено: {item['date']} {item['start']}-{item['end']}",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(F.text == BTN_DELETE_ONE_TIME_WINDOW)
    async def admin_settings_delete_one_time_window_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_delete_one_time_window)
        await state.update_data(
            admin_delete_one_time_window_step="week",
            admin_delete_one_time_window_week_options=_build_future_week_options(),
            admin_delete_one_time_window_day_options={},
        )
        data = await state.get_data()
        week_options = data.get("admin_delete_one_time_window_week_options", {})
        await message.answer(
            "Удалить разовое окно: шаг 1/2. Выберите неделю.",
            reply_markup=slot_selection_keyboard(list(week_options.keys()), add_back=True, columns=1),
        )

    @router.message(BookingForm.admin_delete_one_time_window)
    async def admin_settings_delete_one_time_window_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        if await _maybe_exit_admin_state(message, state):
            return
        text = (message.text or "").strip()
        data = await state.get_data()
        step = data.get("admin_delete_one_time_window_step")

        if _is_back_text(text):
            if step == "day":
                week_options = data.get("admin_delete_one_time_window_week_options", {})
                await state.update_data(admin_delete_one_time_window_step="week")
                await message.answer(
                    "Удалить разовое окно: шаг 1/2. Выберите неделю.",
                    reply_markup=slot_selection_keyboard(list(week_options.keys()), add_back=True, columns=1),
                )
                return
            await state.clear()
            await admin_windows_menu(message, state)
            return

        if step == "week":
            week_options = data.get("admin_delete_one_time_window_week_options", {})
            if text not in week_options:
                await message.answer("Выберите неделю кнопкой из списка.")
                return
            week_start = _parse_date(week_options[text])
            day_options = _build_week_days_options(week_start)
            await state.update_data(
                admin_delete_one_time_window_step="day",
                admin_delete_one_time_window_day_options=day_options,
            )
            await message.answer(
                "Удалить разовое окно: шаг 2/2. Выберите дату.",
                reply_markup=slot_selection_keyboard(list(day_options.keys()), add_back=True, columns=1),
            )
            return

        if step != "day":
            await state.clear()
            await admin_windows_menu(message, state)
            return

        day_options = data.get("admin_delete_one_time_window_day_options", {})
        if text not in day_options:
            await message.answer("Выберите дату кнопкой из списка.")
            return
        target_date = _parse_date(day_options[text])
        deleted = admin_service.remove_one_time_windows_by_date(target_date=target_date)
        await state.clear()
        await message.answer(
            f"Удалено разовых окон на {target_date.isoformat()}: {deleted}",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(F.text == BTN_BLOCK_USER)
    @router.message(F.text == "Блокировать пользователя")
    async def admin_settings_block_user_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_block_user)
        await message.answer(
            "Введите Telegram user ID пользователя для блокировки.",
            reply_markup=admin_manual_entry_keyboard(),
        )

    @router.message(BookingForm.admin_block_user)
    async def admin_settings_block_user_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        if await _maybe_exit_admin_state(message, state):
            return
        raw = (message.text or "").strip()
        try:
            telegram_user_id = int(raw)
            canceled = admin_service.block_user(telegram_user_id=telegram_user_id)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer(
            f"Пользователь {telegram_user_id} заблокирован. Отменено будущих заявок: {len(canceled)}",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(F.text == BTN_UNBLOCK_USER)
    @router.message(F.text == "Разблокировать пользователя")
    async def admin_settings_unblock_user_button(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        await state.set_state(BookingForm.admin_unblock_user)
        await message.answer(
            "Введите Telegram user ID пользователя для разблокировки.",
            reply_markup=admin_manual_entry_keyboard(),
        )

    @router.message(BookingForm.admin_unblock_user)
    async def admin_settings_unblock_user_input(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_access(message):
            return
        if await _maybe_exit_admin_state(message, state):
            return
        raw = (message.text or "").strip()
        try:
            telegram_user_id = int(raw)
            admin_service.unblock_user(telegram_user_id=telegram_user_id)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        await message.answer(
            f"Пользователь {telegram_user_id} разблокирован.",
            reply_markup=admin_settings_keyboard(),
        )

    @router.message(Command("admin_set_window"))
    async def admin_set_window(message: Message) -> None:
        if not await _ensure_admin_access(message):
            return
        parts = (message.text or "").split()
        if len(parts) != 4:
            await message.answer("Формат: /admin_set_window <weekday 0-6> <HH:MM> <HH:MM>")
            return
        try:
            weekday = int(parts[1])
            start_at = _parse_time(parts[2])
            end_at = _parse_time(parts[3])
            rule = admin_service.set_working_window(weekday=weekday, start_at=start_at, end_at=end_at)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await message.answer(
            f"Окно добавлено: rule_id={rule.id}, день={WEEKDAY_NAMES.get(weekday, weekday)}, {parts[2]}-{parts[3]}"
        )

    @router.message(Command("admin_clear_windows"))
    async def admin_clear_windows(message: Message) -> None:
        if not await _ensure_admin_access(message):
            return
        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer("Формат: /admin_clear_windows <weekday|all>")
            return
        try:
            weekday = None if parts[1].lower() == "all" else int(parts[1])
            deleted = admin_service.clear_working_windows(weekday=weekday)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await message.answer(f"Удалено окон: {deleted}")

    @router.message(Command("admin_set_min_lead"))
    async def admin_set_min_lead(message: Message) -> None:
        if not await _ensure_admin_access(message):
            return
        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer("Формат: /admin_set_min_lead <minutes>")
            return
        try:
            minutes = int(parts[1])
            admin_service.set_min_lead_minutes(minutes)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await message.answer(f"Минимальный срок подачи заявки обновлен: {minutes} минут.")

    @router.message(Command("admin_add_block"))
    async def admin_add_block(message: Message) -> None:
        if not await _ensure_admin_access(message):
            return
        parts = (message.text or "").split(maxsplit=4)
        if len(parts) < 4:
            await message.answer("Формат: /admin_add_block <YYYY-MM-DD> <HH:MM> <HH:MM> [comment]")
            return
        try:
            target_date = _parse_date(parts[1])
            start_at = _parse_time(parts[2])
            end_at = _parse_time(parts[3])
            comment = parts[4] if len(parts) > 4 else None
            block = admin_service.add_time_block(
                target_date=target_date,
                start_at=start_at,
                end_at=end_at,
                comment=comment,
            )
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await message.answer(f"Внутренний блок создан: id={block.id} {parts[1]} {parts[2]}-{parts[3]}")

    @router.message(Command("admin_close_date"))
    async def admin_close_date(message: Message) -> None:
        if not await _ensure_admin_access(message):
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 2:
            await message.answer("Формат: /admin_close_date <YYYY-MM-DD> [reason]")
            return
        try:
            target_date = _parse_date(parts[1])
            reason = parts[2] if len(parts) > 2 else None
            await _execute_close_day(message, target_date=target_date, reason=reason)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return

    @router.message(Command("admin_search"))
    async def admin_search(message: Message) -> None:
        if not message.from_user:
            return
        if user_service.resolve_role(message.from_user.id, settings.ADMIN_USER_ID) != UserRole.ADMIN:
            await message.answer("Доступно только администратору.")
            return
        params: dict[str, str] = {}
        for token in (message.text or "").split()[1:]:
            if "=" in token:
                k, v = token.split("=", 1)
                params[k.strip().lower()] = v.strip()
        try:
            rows = admin_service.search_bookings(
                status=params.get("status"),
                target_date=_parse_date(params["date"]) if "date" in params else None,
                name=params.get("name"),
                email=params.get("email"),
                telegram_user_id=int(params["tg"]) if "tg" in params else None,
                limit=50,
            )
        except Exception as exc:
            await message.answer(f"Ошибка фильтра: {exc}")
            return
        if not rows:
            await message.answer("По фильтру ничего не найдено.")
            return
        await message.answer(f"Найдено заявок: {len(rows)}")
        for booking, user in rows:
            await message.answer(
                f"{_format_booking_list_line(booking)}\n"
                f"Пользователь: {user.name or user.telegram_display_name or '—'} | "
                f"email: {user.email or '—'} | tg: {user.telegram_user_id}"
            )

    @router.message(Command("admin_block_user"))
    async def admin_block_user(message: Message) -> None:
        if not message.from_user:
            return
        if user_service.resolve_role(message.from_user.id, settings.ADMIN_USER_ID) != UserRole.ADMIN:
            await message.answer("Доступно только администратору.")
            return
        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer("Формат: /admin_block_user <telegram_user_id>")
            return
        try:
            telegram_user_id = int(parts[1])
            canceled = admin_service.block_user(telegram_user_id=telegram_user_id)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await message.answer(
            f"Пользователь {telegram_user_id} заблокирован. Отменено будущих заявок: {len(canceled)}"
        )

    @router.message(Command("admin_unblock_user"))
    async def admin_unblock_user(message: Message) -> None:
        if not message.from_user:
            return
        if user_service.resolve_role(message.from_user.id, settings.ADMIN_USER_ID) != UserRole.ADMIN:
            await message.answer("Доступно только администратору.")
            return
        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer("Формат: /admin_unblock_user <telegram_user_id>")
            return
        try:
            telegram_user_id = int(parts[1])
            admin_service.unblock_user(telegram_user_id=telegram_user_id)
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await message.answer(f"Пользователь {telegram_user_id} разблокирован.")

    @router.message(Command("admin_bookings"))
    @router.message(F.text == BTN_ADMIN_BOOKINGS)
    @router.message(F.text == "Админ: заявки")
    async def show_admin_bookings(message: Message) -> None:
        if not message.from_user:
            return
        role = user_service.resolve_role(message.from_user.id, settings.ADMIN_USER_ID)
        if role != UserRole.ADMIN:
            await message.answer("Доступно только администратору.")
            return

        await message.answer(
            "Раздел заявок администратора. Выберите, что показать:",
            reply_markup=admin_bookings_view_keyboard(),
        )
        await _send_admin_queue_bookings(message)

    async def _send_admin_queue_bookings(message: Message) -> None:
        bookings = booking_service.list_pending_decision_bookings(limit=20)
        if not bookings:
            await message.answer("В очереди админ-решений сейчас нет заявок.")
            return

        logger.info(
            "Admin pending bookings opened: admin_telegram_user_id=%s count=%s",
            message.from_user.id,
            len(bookings),
        )
        await message.answer(f"Заявок в очереди админ-решения: {len(bookings)}")
        for booking in bookings:
            user = user_service.get_user_by_id(booking.user_id)
            logger.info("Admin booking card opened: booking_id=%s", booking.id)
            await message.answer(
                _format_admin_booking_card(booking, user),
                reply_markup=admin_booking_actions_keyboard(booking.id),
            )

    async def _send_admin_confirmed_bookings(message: Message) -> None:
        bookings = booking_service.list_confirmed_bookings(limit=20)
        if not bookings:
            await message.answer("Подтвержденных заявок пока нет.")
            return

        logger.info(
            "Admin confirmed bookings opened: admin_telegram_user_id=%s count=%s",
            message.from_user.id if message.from_user else None,
            len(bookings),
        )
        await message.answer(f"✅ Подтвержденных заявок: {len(bookings)}")
        for booking in bookings:
            user = user_service.get_user_by_id(booking.user_id)
            await message.answer(
                _format_admin_booking_card(booking, user),
                reply_markup=admin_confirmed_booking_actions_keyboard(booking.id),
            )

    @router.callback_query(F.data == "admin:view:queue")
    async def admin_view_queue_bookings(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        role = user_service.resolve_role(callback.from_user.id, settings.ADMIN_USER_ID)
        if role != UserRole.ADMIN:
            await callback.answer("Недостаточно прав.", show_alert=True)
            return
        if callback.message:
            await _send_admin_queue_bookings(callback.message)
        await callback.answer()

    @router.callback_query(F.data == "admin:view:confirmed")
    async def admin_view_confirmed_bookings(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        role = user_service.resolve_role(callback.from_user.id, settings.ADMIN_USER_ID)
        if role != UserRole.ADMIN:
            await callback.answer("Недостаточно прав.", show_alert=True)
            return
        if callback.message:
            await _send_admin_confirmed_bookings(callback.message)
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:confirm:"))
    async def admin_confirm_booking(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        role = user_service.resolve_role(callback.from_user.id, settings.ADMIN_USER_ID)
        if role != UserRole.ADMIN:
            await callback.answer("Недостаточно прав.", show_alert=True)
            return

        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return
        try:
            result = booking_service.confirm_booking_by_admin(
                booking_id=booking_id,
                admin_telegram_user_id=callback.from_user.id,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        except Exception:
            logger.exception("Admin confirm failed: booking_id=%s", booking_id)
            await callback.answer("Ошибка при подтверждении. Проверьте логи.", show_alert=True)
            return
        logger.info(
            "Admin booking confirmed via callback: booking_id=%s admin_telegram_user_id=%s",
            booking_id,
            callback.from_user.id,
        )

        if callback.message:
            await callback.message.edit_text(
                _format_admin_booking_card(result.booking, result.user),
                reply_markup=None,
            )
            await callback.message.answer(
                f"Заявка #{result.booking.id} подтверждена. Event ID: {result.booking.calendar_event_id or '—'}"
            )
        await callback.answer("Подтверждено.")

        await notify_user_result(
            callback=callback,
            user_telegram_user_id=result.user.telegram_user_id,
            text=(
                "✅ Встреча подтверждена.\n\n"
                + _format_booking_card_line(result.booking, include_status_badge=False)
                + "\nЕсли планы изменятся, откройте «📂 Мои заявки» и выберите действие."
            ),
        )

    @router.callback_query(F.data.startswith("admin:cancel_confirmed:"))
    async def admin_cancel_confirmed_booking(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        role = user_service.resolve_role(callback.from_user.id, settings.ADMIN_USER_ID)
        if role != UserRole.ADMIN:
            await callback.answer("Недостаточно прав.", show_alert=True)
            return

        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        try:
            result = booking_service.cancel_confirmed_booking_by_admin(
                booking_id=booking_id,
                admin_telegram_user_id=callback.from_user.id,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        except Exception:
            logger.exception("Admin cancel confirmed failed: booking_id=%s", booking_id)
            await callback.answer("Ошибка при отмене заявки. Проверьте логи.", show_alert=True)
            return

        if callback.message:
            await callback.message.edit_text(
                _format_admin_booking_card(result.booking, result.user),
                reply_markup=None,
            )
            await callback.message.answer("Подтвержденная заявка отменена.")
        await callback.answer("Отменено.")

        await notify_user_result(
            callback=callback,
            user_telegram_user_id=result.user.telegram_user_id,
            text=(
                "🚫 Ваша встреча отменена администратором.\n"
                "При необходимости создайте новую заявку через «📝 Новая заявка»."
            ),
        )

    @router.callback_query(F.data.startswith("admin:reject:"))
    async def admin_reject_booking(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        role = user_service.resolve_role(callback.from_user.id, settings.ADMIN_USER_ID)
        if role != UserRole.ADMIN:
            await callback.answer("Недостаточно прав.", show_alert=True)
            return

        payload = callback.data or ""
        try:
            booking_id = int(payload.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректная команда.", show_alert=True)
            return
        try:
            result = booking_service.reject_booking_by_admin(
                booking_id=booking_id,
                admin_telegram_user_id=callback.from_user.id,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        except Exception:
            logger.exception("Admin reject failed: booking_id=%s", booking_id)
            await callback.answer("Ошибка при отклонении. Проверьте логи.", show_alert=True)
            return
        logger.info(
            "Admin booking rejected via callback: booking_id=%s admin_telegram_user_id=%s",
            booking_id,
            callback.from_user.id,
        )

        if callback.message:
            await callback.message.edit_text(
                _format_admin_booking_card(result.booking, result.user),
                reply_markup=None,
            )
            await callback.message.answer(f"Заявка #{result.booking.id} отклонена.")
        await callback.answer("Отклонено.")

        await notify_user_result(
            callback=callback,
            user_telegram_user_id=result.user.telegram_user_id,
            text=(
                "❌ Заявка не подтверждена.\n"
                "Слот освобожден. Вы можете создать новую заявку в любое время."
            ),
        )

    return router
