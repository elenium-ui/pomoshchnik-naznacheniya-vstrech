from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.services.booking_validation import (
    parse_optional_comment,
    parse_optional_email,
    validate_name,
    validate_phone,
)
from app.config import load_settings
from app.web.api.notifications import send_telegram_text
from app.web.api.dependencies.auth import get_auth_service
from app.web.api.dependencies.services import MiniAppCoreServices, get_core_services
from app.web.api.schemas.booking_flow import BookingSlotsResponse, SlotOption, SlotTimeOption
from app.web.api.schemas.client_cabinet import (
    ClientBookingActionRequest,
    ClientBookingActionResponse,
    ClientBookingItem,
    ClientBookingsListResponse,
    ClientJoinWaitlistRequest,
    ClientProfilePayload,
    ClientProfileResponse,
    ClientProfileUpdateRequest,
    ClientRescheduleStartResponse,
    ClientRescheduleSubmitRequest,
)
from app.web.services.auth import MiniAppAuthService, TelegramInitDataError

router = APIRouter(prefix="/api/miniapp/client")
logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")


def _slot_key(start_at: datetime) -> str:
    return start_at.strftime("%Y-%m-%d %H:%M")


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


def _build_slot_hierarchy(slots_by_date: Dict) -> Tuple[BookingSlotsResponse, Dict[str, Tuple[datetime, datetime]]]:
    week_options: List[SlotOption] = []
    day_options_by_week: Dict[str, List[SlotOption]] = {}
    time_options_by_day: Dict[str, List[SlotTimeOption]] = {}
    key_to_slot: Dict[str, Tuple[datetime, datetime]] = {}
    seen_week_keys: set[str] = set()

    for day in sorted(slots_by_date.keys()):
        day_slots = slots_by_date[day]
        if not day_slots:
            continue

        week_start = day - timedelta(days=day.weekday())
        week_end = week_start + timedelta(days=6)
        week_key = week_start.isoformat()
        if week_key not in seen_week_keys:
            seen_week_keys.add(week_key)
            week_options.append(
                SlotOption(
                    label=f"Неделя {week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')}",
                    key=week_key,
                )
            )

        day_key = day.isoformat()
        slots_count = len(day_slots)
        day_label = f"{day.strftime('%a %d.%m')} ({slots_count} {_slots_word(slots_count)})"
        day_options_by_week.setdefault(week_key, []).append(SlotOption(label=day_label, key=day_key))
        time_options_by_day.setdefault(day_key, [])

        for slot in day_slots:
            slot_identifier = _slot_key(slot.start_at)
            key_to_slot[slot_identifier] = (slot.start_at, slot.end_at)
            time_options_by_day[day_key].append(
                SlotTimeOption(
                    label=slot.start_at.strftime("%H:%M"),
                    slot_key=slot_identifier,
                    starts_at=slot.start_at,
                    ends_at=slot.end_at,
                )
            )

    total_slots = len(key_to_slot)
    non_empty_days = sum(1 for day_slots in slots_by_date.values() if day_slots)
    return (
        BookingSlotsResponse(
            total_slots=total_slots,
            non_empty_days=non_empty_days,
            week_options=week_options,
            day_options_by_week=day_options_by_week,
            time_options_by_day=time_options_by_day,
        ),
        key_to_slot,
    )


def _display_name(first_name: str | None, last_name: str | None, username: str | None) -> str:
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if full_name:
        return full_name
    if username:
        return username
    return "Пользователь"


def _format_name(user) -> str:
    return user.name or user.telegram_display_name or "—"


def _format_telegram_username(user) -> str:
    username = (user.telegram_username or "").strip()
    if not username:
        return "не указан"
    return f"@{username}" if not username.startswith("@") else username


def _resolve_user(init_data: str, auth_service: MiniAppAuthService, core: MiniAppCoreServices):
    try:
        session = auth_service.build_session(init_data)
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App authorization failed.",
        ) from exc

    display_name = _display_name(
        first_name=session.user.first_name,
        last_name=session.user.last_name,
        username=session.user.username,
    )
    user = core.user_service.ensure_user_from_telegram(
        telegram_user_id=session.user.telegram_user_id,
        telegram_username=session.user.username,
        telegram_display_name=display_name,
    )
    return session, user


def _as_google_calendar_dt(dt_value: datetime) -> str:
    msk_aware = dt_value.replace(tzinfo=MSK) if dt_value.tzinfo is None else dt_value.astimezone(MSK)
    return msk_aware.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def _build_google_calendar_url(booking) -> str | None:
    if booking.slot_start_at is None or booking.slot_end_at is None:
        return None
    title = booking.topic or "Встреча"
    details = booking.comment or "Заявка из Telegram Mini App"
    dates = f"{_as_google_calendar_dt(booking.slot_start_at)}/{_as_google_calendar_dt(booking.slot_end_at)}"
    return (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={quote_plus(title)}"
        f"&dates={quote_plus(dates)}"
        f"&details={quote_plus(details)}"
        "&ctz=Europe/Moscow"
    )


def _to_booking_item(booking) -> ClientBookingItem:
    return ClientBookingItem(
        booking_id=booking.id,
        status=booking.status,
        topic=booking.topic,
        meeting_format=booking.format,
        duration_minutes=booking.duration_minutes,
        waitlist_date=booking.waitlist_date,
        slot_start_at=booking.slot_start_at,
        slot_end_at=booking.slot_end_at,
        offered_slot_start_at=booking.requested_new_slot_start_at,
        offered_slot_end_at=booking.requested_new_slot_end_at,
        comment=booking.comment,
        admin_public_comment=booking.admin_public_comment,
        meeting_link=booking.meeting_link,
        calendar_event_id=booking.calendar_event_id,
        google_calendar_url=_build_google_calendar_url(booking),
        is_urgent=bool(getattr(booking, "is_urgent", False)),
        updated_at=booking.updated_at,
    )


@router.get("/bookings/active", response_model=ClientBookingsListResponse)
def get_active_bookings(
    init_data: str = Query(..., min_length=1),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientBookingsListResponse:
    _, user = _resolve_user(init_data, auth_service=auth_service, core=core)
    now_msk_naive = datetime.now(MSK).replace(tzinfo=None)
    items = [
        _to_booking_item(item)
        for item in core.booking_service.list_active_bookings(
            user_id=user.id,
            now_msk_naive=now_msk_naive,
        )
    ]
    logger.info("Mini App client active bookings loaded: user_id=%s count=%s", user.id, len(items))
    return ClientBookingsListResponse(items=items)


@router.get("/bookings/history", response_model=ClientBookingsListResponse)
def get_history_bookings(
    init_data: str = Query(..., min_length=1),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientBookingsListResponse:
    _, user = _resolve_user(init_data, auth_service=auth_service, core=core)
    now_msk_naive = datetime.now(MSK).replace(tzinfo=None)
    items = [
        _to_booking_item(item)
        for item in core.booking_service.list_history_bookings(
            user_id=user.id,
            now_msk_naive=now_msk_naive,
        )
    ]
    logger.info("Mini App client history loaded: user_id=%s count=%s", user.id, len(items))
    return ClientBookingsListResponse(items=items)


@router.post("/bookings/{booking_id}/cancel", response_model=ClientBookingActionResponse)
def cancel_booking(
    booking_id: int,
    payload: ClientBookingActionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientBookingActionResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    try:
        booking = core.booking_service.cancel_booking_by_user(
            booking_id=booking_id,
            user_id=user.id,
            user_telegram_user_id=session.user.telegram_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info("Mini App client cancel action: booking_id=%s user_id=%s", booking.id, user.id)
    return ClientBookingActionResponse(
        booking_id=booking.id,
        status=booking.status,
        message="Заявка отменена.",
    )


@router.post("/bookings/{booking_id}/reschedule/start", response_model=ClientRescheduleStartResponse)
def start_reschedule(
    booking_id: int,
    payload: ClientBookingActionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientRescheduleStartResponse:
    _, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    try:
        booking = core.booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if booking.status not in {"pending_decision", "confirmed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Запустить перенос можно только для заявки в ожидании или подтвержденной.",
        )
    if booking.slot_start_at is None or booking.slot_end_at is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="У заявки нет активного слота для переноса.",
        )
    if not booking.duration_minutes or booking.duration_minutes <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="У заявки не указана длительность для подбора переноса.",
        )

    slots_by_date = core.availability_service.get_available_slots(duration_minutes=booking.duration_minutes)
    hierarchy, _ = _build_slot_hierarchy(slots_by_date)

    logger.info(
        "Mini App client reschedule started: booking_id=%s user_id=%s duration=%s slots=%s",
        booking.id,
        user.id,
        booking.duration_minutes,
        hierarchy.total_slots,
    )
    return ClientRescheduleStartResponse(
        booking_id=booking.id,
        status=booking.status,
        duration_minutes=booking.duration_minutes,
        current_slot_start_at=booking.slot_start_at,
        current_slot_end_at=booking.slot_end_at,
        available_slots=hierarchy,
        message="Сценарий переноса запущен. Выберите новый слот.",
    )


@router.post("/bookings/{booking_id}/reschedule/submit", response_model=ClientBookingActionResponse)
def submit_reschedule(
    booking_id: int,
    payload: ClientRescheduleSubmitRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientBookingActionResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    try:
        booking = core.booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if booking.status not in {"pending_decision", "confirmed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Запросить перенос можно только для заявки в ожидании или подтвержденной.",
        )
    if not booking.duration_minutes or booking.duration_minutes <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="У заявки не указана длительность для подбора переноса.",
        )

    slots_by_date = core.availability_service.get_available_slots(duration_minutes=booking.duration_minutes)
    _, key_to_slot = _build_slot_hierarchy(slots_by_date)
    if payload.slot_key not in key_to_slot:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Выбранный слот недоступен.")

    selected_start_at, selected_end_at = key_to_slot[payload.slot_key]
    expires_at = (datetime.now(MSK) + timedelta(hours=72)).replace(tzinfo=None)
    try:
        updated = core.booking_service.request_reschedule_by_user(
            booking_id=booking.id,
            user_id=user.id,
            user_telegram_user_id=session.user.telegram_user_id,
            requested_start_at_msk_naive=selected_start_at.replace(tzinfo=None),
            requested_end_at_msk_naive=selected_end_at.replace(tzinfo=None),
            expires_at_msk_naive=expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info(
        "Mini App client reschedule submitted: booking_id=%s user_id=%s slot_key=%s",
        updated.id,
        user.id,
        payload.slot_key,
    )
    send_telegram_text(
        chat_id=load_settings().ADMIN_USER_ID,
        text=(
            "Клиент запросил перенос встречи (Mini App)\n\n"
            f"ID заявки: {updated.id}\n"
            f"Пользователь: {_format_name(user)}\n"
            f"Telegram: {_format_telegram_username(user)}\n"
            f"Новый слот: "
            f"{updated.requested_new_slot_start_at.strftime('%d.%m.%Y %H:%M') if updated.requested_new_slot_start_at else '—'}"
        ),
    )
    return ClientBookingActionResponse(
        booking_id=updated.id,
        status=updated.status,
        message="Запрос на перенос отправлен администратору.",
    )


@router.post("/bookings/{booking_id}/waitlist", response_model=ClientBookingActionResponse)
def join_waitlist_from_client_cabinet(
    booking_id: int,
    payload: ClientJoinWaitlistRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientBookingActionResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    today = datetime.now(MSK).date()
    if payload.waitlist_date < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Нельзя добавить в лист ожидания прошедшую дату.",
        )
    max_date = today + timedelta(days=120)
    if payload.waitlist_date > max_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Дата листа ожидания слишком далеко. Выберите дату ближе.",
        )
    waitlist_comment = parse_optional_comment(payload.waitlist_comment or "")
    if not waitlist_comment:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Добавьте комментарий для листа ожидания: почему нужна именно эта дата.",
        )
    try:
        updated = core.booking_service.join_waitlist(
            booking_id=booking_id,
            user_id=user.id,
            user_telegram_user_id=session.user.telegram_user_id,
            waitlist_date_value=payload.waitlist_date,
            waitlist_comment=waitlist_comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info(
        "Mini App client waitlist joined via client route: booking_id=%s user_id=%s waitlist_date=%s",
        updated.id,
        user.id,
        payload.waitlist_date.isoformat(),
    )
    send_telegram_text(
        chat_id=load_settings().ADMIN_USER_ID,
        text=(
            "Клиент добавил заявку в лист ожидания (Mini App)\n\n"
            f"ID заявки: {updated.id}\n"
            f"Пользователь: {_format_name(user)}\n"
            f"Telegram: {_format_telegram_username(user)}\n"
            f"Дата ожидания: {payload.waitlist_date.strftime('%d.%m.%Y')}"
        ),
    )
    return ClientBookingActionResponse(
        booking_id=updated.id,
        status=updated.status,
        message="Добавили в лист ожидания. Администратор предложит доступный слот.",
    )


@router.post("/bookings/{booking_id}/waitlist/accept", response_model=ClientBookingActionResponse)
def accept_waitlist_offer(
    booking_id: int,
    payload: ClientBookingActionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientBookingActionResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    expires_at = (datetime.now(MSK) + timedelta(hours=72)).replace(tzinfo=None)
    try:
        updated = core.booking_service.accept_waitlist_offer_by_user(
            booking_id=booking_id,
            user_id=user.id,
            user_telegram_user_id=session.user.telegram_user_id,
            expires_at_msk_naive=expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info(
        "Mini App client accepted waitlist offer: booking_id=%s user_id=%s",
        updated.id,
        user.id,
    )
    send_telegram_text(
        chat_id=load_settings().ADMIN_USER_ID,
        text=(
            "Клиент принял предложенный слот (Mini App)\n\n"
            f"ID заявки: {updated.id}\n"
            f"Пользователь: {_format_name(user)}\n"
            f"Telegram: {_format_telegram_username(user)}\n"
            f"Слот: {updated.slot_start_at.strftime('%d.%m.%Y %H:%M') if updated.slot_start_at else '—'}"
        ),
    )
    return ClientBookingActionResponse(
        booking_id=updated.id,
        status=updated.status,
        message="Слот принят. Заявка снова ожидает решения администратора.",
    )


@router.post("/bookings/{booking_id}/waitlist/reject", response_model=ClientBookingActionResponse)
def reject_waitlist_offer(
    booking_id: int,
    payload: ClientBookingActionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientBookingActionResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    try:
        updated = core.booking_service.reject_waitlist_offer_by_user(
            booking_id=booking_id,
            user_id=user.id,
            user_telegram_user_id=session.user.telegram_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info(
        "Mini App client rejected waitlist offer: booking_id=%s user_id=%s",
        updated.id,
        user.id,
    )
    send_telegram_text(
        chat_id=load_settings().ADMIN_USER_ID,
        text=(
            "Клиент отклонил предложенный слот (Mini App)\n\n"
            f"ID заявки: {updated.id}\n"
            f"Пользователь: {_format_name(user)}\n"
            f"Telegram: {_format_telegram_username(user)}"
        ),
    )
    return ClientBookingActionResponse(
        booking_id=updated.id,
        status=updated.status,
        message="Предложенный слот отклонён. Заявка возвращена в лист ожидания.",
    )


@router.get("/profile", response_model=ClientProfileResponse)
def get_profile(
    init_data: str = Query(..., min_length=1),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientProfileResponse:
    _, user = _resolve_user(init_data, auth_service=auth_service, core=core)
    logger.info("Mini App client profile loaded: user_id=%s", user.id)
    return ClientProfileResponse(
        profile=ClientProfilePayload(
            name=user.name,
            email=user.email,
            phone=user.phone,
            telegram_username=user.telegram_username,
            reminder_supported=True,
            reminder_enabled=bool(getattr(user, "reminder_enabled", False)),
        )
    )


def _update_profile_impl(
    payload: ClientProfileUpdateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientProfileResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)

    name_value = None
    if payload.name is not None and payload.name.strip():
        try:
            name_value = validate_name(payload.name)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    try:
        email_value = parse_optional_email(payload.email or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    try:
        phone_value = validate_phone(payload.phone or "") if payload.phone else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    updated = core.user_service.update_user_profile(
        telegram_user_id=session.user.telegram_user_id,
        name=name_value,
        email=email_value,
        phone=phone_value,
        reminder_enabled=payload.reminder_enabled,
    )
    logger.info("Mini App client profile updated: user_id=%s", user.id)
    return ClientProfileResponse(
        profile=ClientProfilePayload(
            name=updated.name,
            email=updated.email,
            phone=updated.phone,
            telegram_username=updated.telegram_username,
            reminder_supported=True,
            reminder_enabled=bool(getattr(updated, "reminder_enabled", False)),
        )
    )


@router.put("/profile", response_model=ClientProfileResponse)
def update_profile_put(
    payload: ClientProfileUpdateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientProfileResponse:
    return _update_profile_impl(payload=payload, auth_service=auth_service, core=core)


@router.post("/profile", response_model=ClientProfileResponse)
def update_profile_post(
    payload: ClientProfileUpdateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> ClientProfileResponse:
    return _update_profile_impl(payload=payload, auth_service=auth_service, core=core)
