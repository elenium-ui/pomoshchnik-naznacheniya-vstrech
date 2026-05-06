from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status

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
from app.config import load_settings
from app.web.api.notifications import send_telegram_text
from app.web.api.dependencies.auth import get_auth_service
from app.web.api.dependencies.services import MiniAppCoreServices, get_core_services
from app.web.api.schemas.booking_flow import (
    ActiveDraftPayload,
    BookingProfilePayload,
    BookingSlotsResponse,
    InitDataPayload,
    JoinWaitlistRequest,
    JoinWaitlistResponse,
    SaveBookingDraftRequest,
    SaveBookingDraftResponse,
    SlotOption,
    SlotTimeOption,
    StartBookingSessionRequest,
    StartBookingSessionResponse,
    SubmitBookingRequest,
    SubmittedBookingPayload,
)
from app.web.services.auth import MiniAppAuthService, TelegramInitDataError

router = APIRouter(prefix="/api/miniapp/bookings")
logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")
FUTURE_ACTIVE_LIMIT: int | None = None


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


@router.post("/new/session", response_model=StartBookingSessionResponse)
def start_booking_session(
    payload: StartBookingSessionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> StartBookingSessionResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)

    if core.user_service.is_blocked(session.user.telegram_user_id):
        logger.warning("Mini App booking start denied: blocked user tg_user_id=%s", session.user.telegram_user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="New bookings are disabled for this account.",
        )

    active_count = core.booking_service.count_future_active_for_limit(
        user_id=user.id,
        now_msk_naive=datetime.now(MSK).replace(tzinfo=None),
    )
    if FUTURE_ACTIVE_LIMIT is not None and active_count >= FUTURE_ACTIVE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Future active booking limit reached.",
        )

    if payload.start_over:
        discarded = core.booking_service.discard_active_draft(
            user_id=user.id,
            user_telegram_user_id=session.user.telegram_user_id,
        )
        if discarded is not None:
            logger.info(
                "Mini App active draft discarded by request: booking_id=%s user_id=%s tg_user_id=%s",
                discarded.id,
                user.id,
                session.user.telegram_user_id,
            )

    booking, reused_existing = core.booking_service.create_or_get_active_draft(user_id=user.id)
    logger.info(
        "Mini App draft loaded: booking_id=%s user_id=%s tg_user_id=%s reused_existing=%s",
        booking.id,
        user.id,
        session.user.telegram_user_id,
        reused_existing,
    )
    return StartBookingSessionResponse(
        booking_id=booking.id,
        future_active_count=active_count,
        future_active_limit=FUTURE_ACTIVE_LIMIT or 0,
        profile=BookingProfilePayload(
            name=user.name,
            email=user.email,
            phone=user.phone,
            telegram_username=user.telegram_username,
        ),
        has_active_draft=reused_existing,
        active_draft=(
            ActiveDraftPayload(
                booking_id=booking.id,
                topic=booking.topic,
                meeting_format=booking.format,
                duration_minutes=booking.duration_minutes,
                email=user.email,
                phone=user.phone,
                comment=booking.comment,
                is_urgent=bool(booking.is_urgent),
            )
            if reused_existing
            else None
        ),
    )


@router.put("/{booking_id}/details", response_model=SaveBookingDraftResponse)
@router.post("/{booking_id}/details", response_model=SaveBookingDraftResponse)
def save_booking_details(
    booking_id: int,
    payload: SaveBookingDraftRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> SaveBookingDraftResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)

    try:
        name = validate_name(payload.name)
        topic = validate_topic(payload.topic)
        meeting_format = validate_meeting_format(payload.meeting_format)
        duration_minutes = validate_duration(str(payload.duration_minutes))
        email = parse_optional_email(payload.email or "")
        phone = validate_phone(payload.phone or "") if payload.phone else None
        comment = parse_optional_comment(payload.comment or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    has_username = bool(user.telegram_username)
    if requires_alternative_contact(has_username=has_username, email=email) and not phone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Phone is required when Telegram username and email are missing.",
        )

    core.user_service.update_user_profile(
        telegram_user_id=session.user.telegram_user_id,
        name=name,
        email=email,
        phone=phone,
    )

    try:
        booking = core.booking_service.update_booking_fields(
            booking_id=booking_id,
            user_id=user.id,
            topic=topic,
            format=meeting_format,
            duration_minutes=duration_minutes,
            comment=comment,
            is_urgent=bool(payload.is_urgent),
            status="draft",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    updated_user = core.user_service.get_user_by_id(user.id)
    logger.info(
        "Mini App booking draft updated: booking_id=%s user_id=%s duration=%s is_urgent=%s",
        booking.id,
        user.id,
        duration_minutes,
        bool(payload.is_urgent),
    )
    return SaveBookingDraftResponse(
        booking_id=booking.id,
        status=booking.status,
        duration_minutes=duration_minutes,
        profile=BookingProfilePayload(
            name=updated_user.name,
            email=updated_user.email,
            phone=updated_user.phone,
            telegram_username=updated_user.telegram_username,
        ),
    )


@router.post("/draft/discard", response_model=SaveBookingDraftResponse)
def discard_active_draft(
    payload: InitDataPayload,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> SaveBookingDraftResponse:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    discarded = core.booking_service.discard_active_draft(
        user_id=user.id,
        user_telegram_user_id=session.user.telegram_user_id,
    )
    if discarded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Активный черновик не найден.")
    updated_user = core.user_service.get_user_by_id(user.id)
    logger.info(
        "Mini App draft discarded: booking_id=%s user_id=%s tg_user_id=%s",
        discarded.id,
        user.id,
        session.user.telegram_user_id,
    )
    return SaveBookingDraftResponse(
        booking_id=discarded.id,
        status=discarded.status,
        duration_minutes=discarded.duration_minutes or 0,
        profile=BookingProfilePayload(
            name=updated_user.name,
            email=updated_user.email,
            phone=updated_user.phone,
            telegram_username=updated_user.telegram_username,
        ),
    )


@router.post("/{booking_id}/waitlist", response_model=JoinWaitlistResponse)
def join_waitlist(
    booking_id: int,
    payload: JoinWaitlistRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> JoinWaitlistResponse:
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
        booking = core.booking_service.join_waitlist(
            booking_id=booking_id,
            user_id=user.id,
            user_telegram_user_id=session.user.telegram_user_id,
            waitlist_date_value=payload.waitlist_date,
            waitlist_comment=waitlist_comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info(
        "Mini App waitlist joined: booking_id=%s user_id=%s tg_user_id=%s waitlist_date=%s",
        booking.id,
        user.id,
        session.user.telegram_user_id,
        payload.waitlist_date.isoformat(),
    )
    admin_text = (
        "Новая заявка в листе ожидания (Mini App)\n\n"
        f"ID: {booking.id}\n"
        f"Пользователь: {_format_name(user)}\n"
        f"Telegram: {_format_telegram_username(user)}\n"
        f"Дата ожидания: {payload.waitlist_date.strftime('%d.%m.%Y')}\n"
        f"Тема: {booking.topic or '—'}"
    )
    send_telegram_text(chat_id=load_settings().ADMIN_USER_ID, text=admin_text)
    return JoinWaitlistResponse(
        booking_id=booking.id,
        status=booking.status,
        waitlist_date=payload.waitlist_date,
        message="Добавили в лист ожидания. Администратор сможет предложить слот на эту дату.",
    )


@router.get("/slots", response_model=BookingSlotsResponse)
def get_slots_for_duration(
    init_data: str = Query(..., min_length=1),
    duration_minutes: int = Query(...),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> BookingSlotsResponse:
    _resolve_user(init_data, auth_service=auth_service, core=core)

    try:
        duration = validate_duration(str(duration_minutes))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    slots_by_date = core.availability_service.get_available_slots(duration_minutes=duration)
    hierarchy, _ = _build_slot_hierarchy(slots_by_date)
    logger.info(
        "Mini App slots requested: duration=%s total_slots=%s non_empty_days=%s",
        duration,
        hierarchy.total_slots,
        hierarchy.non_empty_days,
    )
    return hierarchy


@router.post("/{booking_id}/submit", response_model=SubmittedBookingPayload)
def submit_booking(
    booking_id: int,
    payload: SubmitBookingRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> SubmittedBookingPayload:
    session, user = _resolve_user(payload.init_data, auth_service=auth_service, core=core)
    try:
        booking = core.booking_service.get_booking_for_user(booking_id=booking_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    duration = booking.duration_minutes or 0
    if duration <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Booking duration is not set.",
        )

    slots_by_date = core.availability_service.get_available_slots(duration_minutes=duration)
    _, key_to_slot = _build_slot_hierarchy(slots_by_date)
    if payload.slot_key not in key_to_slot:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Selected slot is no longer available.")

    selected_start_at, selected_end_at = key_to_slot[payload.slot_key]
    expires_at = (datetime.now(MSK) + timedelta(hours=72)).replace(tzinfo=None)
    try:
        submitted = core.booking_service.hold_slot_and_submit(
            booking_id=booking.id,
            user_id=user.id,
            slot_start_at_msk_naive=selected_start_at.replace(tzinfo=None),
            slot_end_at_msk_naive=selected_end_at.replace(tzinfo=None),
            expires_at_msk_naive=expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info(
        "Mini App booking submitted: booking_id=%s user_id=%s tg_user_id=%s slot_key=%s",
        submitted.id,
        user.id,
        session.user.telegram_user_id,
        payload.slot_key,
    )
    admin_text = (
        "Новая заявка из Mini App\n\n"
        f"ID: {submitted.id}\n"
        f"Пользователь: {_format_name(user)}\n"
        f"Telegram: {_format_telegram_username(user)}\n"
        f"Тема: {submitted.topic or '—'}\n"
        f"Дата/время: {submitted.slot_start_at.strftime('%d.%m.%Y %H:%M') if submitted.slot_start_at else '—'}\n"
        f"Формат: {submitted.format or '—'}"
    )
    send_telegram_text(
        chat_id=load_settings().ADMIN_USER_ID,
        text=admin_text,
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": "✅ Подтвердить", "callback_data": f"admin:confirm:{submitted.id}"},
                    {"text": "❌ Отклонить", "callback_data": f"admin:reject:{submitted.id}"},
                ]
            ]
        },
    )
    return SubmittedBookingPayload(
        booking_id=submitted.id,
        status=submitted.status,
        topic=submitted.topic,
        meeting_format=submitted.format,
        duration_minutes=submitted.duration_minutes,
        comment=submitted.comment,
        is_urgent=bool(submitted.is_urgent),
        slot_start_at=submitted.slot_start_at,
        slot_end_at=submitted.slot_end_at,
    )
