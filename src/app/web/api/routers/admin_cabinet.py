from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.web.api.dependencies.auth import get_auth_service
from app.web.api.dependencies.services import MiniAppCoreServices, get_core_services
from app.web.api.schemas.admin_cabinet import (
    AdminBookingActionResponse,
    AdminBookingItemPayload,
    AdminOfferWaitlistSlotRequest,
    AdminBookingUserPayload,
    AdminBookingsListResponse,
    AdminDecisionRequest,
    AdminUpdateBookingMetaRequest,
)
from app.web.api.schemas.booking_flow import BookingSlotsResponse, SlotOption, SlotTimeOption
from app.web.services.auth import MiniAppAuthService, TelegramInitDataError

router = APIRouter(prefix="/api/miniapp/admin")
logger = logging.getLogger(__name__)


def _slot_key(start_at) -> str:
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


def _build_slot_hierarchy(slots_by_date):
    week_options: list[SlotOption] = []
    day_options_by_week: dict[str, list[SlotOption]] = {}
    time_options_by_day: dict[str, list[SlotTimeOption]] = {}
    key_to_slot = {}
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

    return (
        BookingSlotsResponse(
            total_slots=len(key_to_slot),
            non_empty_days=sum(1 for day_slots in slots_by_date.values() if day_slots),
            week_options=week_options,
            day_options_by_week=day_options_by_week,
            time_options_by_day=time_options_by_day,
        ),
        key_to_slot,
    )


def _resolve_admin(init_data: str, auth_service: MiniAppAuthService, core: MiniAppCoreServices):
    try:
        session = auth_service.build_session(init_data)
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App authorization failed.",
        ) from exc
    if not session.is_admin:
        logger.warning("Mini App admin access denied: tg_user_id=%s", session.user.telegram_user_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin mode required.")
    user = core.user_service.ensure_user_from_telegram(
        telegram_user_id=session.user.telegram_user_id,
        telegram_username=session.user.username,
        telegram_display_name=session.user.first_name,
    )
    return session, user


def _to_item(booking, user) -> AdminBookingItemPayload:
    return AdminBookingItemPayload(
        booking_id=booking.id,
        status=booking.status,
        topic=booking.topic,
        is_urgent=bool(getattr(booking, "is_urgent", False)),
        meeting_format=booking.format,
        duration_minutes=booking.duration_minutes,
        waitlist_date=booking.waitlist_date,
        slot_start_at=booking.slot_start_at,
        slot_end_at=booking.slot_end_at,
        requested_new_slot_start_at=booking.requested_new_slot_start_at,
        requested_new_slot_end_at=booking.requested_new_slot_end_at,
        comment=booking.comment,
        admin_public_comment=booking.admin_public_comment,
        meeting_link=booking.meeting_link,
        calendar_event_id=booking.calendar_event_id,
        updated_at=booking.updated_at,
        user=AdminBookingUserPayload(
            user_id=user.id,
            telegram_user_id=user.telegram_user_id,
            telegram_username=user.telegram_username,
            name=user.name,
            email=user.email,
            phone=user.phone,
        ),
    )


@router.get("/bookings", response_model=AdminBookingsListResponse)
def list_bookings(
    init_data: str = Query(..., min_length=1),
    status_filter: Optional[str] = Query(default=None),
    date_filter: Optional[date] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> AdminBookingsListResponse:
    _resolve_admin(init_data, auth_service=auth_service, core=core)
    rows = core.booking_service.search_bookings_for_admin(
        status=status_filter,
        target_date=date_filter,
        search=search,
        limit=limit,
    )
    items = [_to_item(booking, user) for booking, user in rows]
    logger.info(
        "Mini App admin bookings loaded: status=%s date=%s search=%s count=%s",
        status_filter,
        date_filter.isoformat() if date_filter else None,
        bool(search),
        len(items),
    )
    return AdminBookingsListResponse(items=items)


@router.get("/bookings/{booking_id}", response_model=AdminBookingItemPayload)
def get_booking(
    booking_id: int,
    init_data: str = Query(..., min_length=1),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> AdminBookingItemPayload:
    _resolve_admin(init_data, auth_service=auth_service, core=core)
    try:
        booking, user = core.booking_service.get_booking_for_admin(booking_id=booking_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    logger.info("Mini App admin booking opened: booking_id=%s", booking_id)
    return _to_item(booking, user)


@router.post("/bookings/{booking_id}/confirm", response_model=AdminBookingActionResponse)
def confirm_booking(
    booking_id: int,
    payload: AdminDecisionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> AdminBookingActionResponse:
    session, _ = _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    comment_value = payload.admin_public_comment.strip() if payload.admin_public_comment else None
    link_value = payload.meeting_link.strip() if payload.meeting_link else None
    if link_value and not (link_value.startswith("http://") or link_value.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ссылка на встречу должна начинаться с http:// или https://",
        )
    try:
        if payload.admin_public_comment is not None or payload.meeting_link is not None:
            core.booking_service.update_booking_admin_fields(
                booking_id=booking_id,
                admin_telegram_user_id=session.user.telegram_user_id,
                admin_public_comment=comment_value,
                meeting_link=link_value,
            )
        result = core.booking_service.confirm_booking_by_admin(
            booking_id=booking_id,
            admin_telegram_user_id=session.user.telegram_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    logger.info("Mini App admin decision confirm: booking_id=%s", booking_id)
    return AdminBookingActionResponse(
        booking_id=result.booking.id,
        status=result.booking.status,
        message="Заявка подтверждена.",
        admin_public_comment=result.booking.admin_public_comment,
        meeting_link=result.booking.meeting_link,
    )


@router.post("/bookings/{booking_id}/reject", response_model=AdminBookingActionResponse)
def reject_booking(
    booking_id: int,
    payload: AdminDecisionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> AdminBookingActionResponse:
    session, _ = _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    comment_value = payload.admin_public_comment.strip() if payload.admin_public_comment else None
    link_value = payload.meeting_link.strip() if payload.meeting_link else None
    if link_value and not (link_value.startswith("http://") or link_value.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ссылка на встречу должна начинаться с http:// или https://",
        )
    try:
        if payload.admin_public_comment is not None or payload.meeting_link is not None:
            core.booking_service.update_booking_admin_fields(
                booking_id=booking_id,
                admin_telegram_user_id=session.user.telegram_user_id,
                admin_public_comment=comment_value,
                meeting_link=link_value,
            )
        result = core.booking_service.reject_booking_by_admin(
            booking_id=booking_id,
            admin_telegram_user_id=session.user.telegram_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info("Mini App admin decision reject: booking_id=%s", booking_id)
    return AdminBookingActionResponse(
        booking_id=result.booking.id,
        status=result.booking.status,
        message="Заявка отклонена.",
        admin_public_comment=result.booking.admin_public_comment,
        meeting_link=result.booking.meeting_link,
    )


@router.put("/bookings/{booking_id}/meta", response_model=AdminBookingActionResponse)
def update_booking_meta(
    booking_id: int,
    payload: AdminUpdateBookingMetaRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> AdminBookingActionResponse:
    session, _ = _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    comment_value = payload.admin_public_comment.strip() if payload.admin_public_comment else None
    link_value = payload.meeting_link.strip() if payload.meeting_link else None
    if link_value and not (link_value.startswith("http://") or link_value.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ссылка на встречу должна начинаться с http:// или https://",
        )
    try:
        booking, _ = core.booking_service.update_booking_admin_fields(
            booking_id=booking_id,
            admin_telegram_user_id=session.user.telegram_user_id,
            admin_public_comment=comment_value,
            meeting_link=link_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    logger.info("Mini App admin booking meta updated: booking_id=%s", booking_id)
    return AdminBookingActionResponse(
        booking_id=booking.id,
        status=booking.status,
        message="Комментарий и ссылка сохранены.",
        admin_public_comment=booking.admin_public_comment,
        meeting_link=booking.meeting_link,
    )


@router.post("/bookings/{booking_id}/waitlist/offer", response_model=AdminBookingActionResponse)
def offer_waitlist_slot(
    booking_id: int,
    payload: AdminOfferWaitlistSlotRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> AdminBookingActionResponse:
    session, _ = _resolve_admin(payload.init_data, auth_service=auth_service, core=core)

    try:
        booking, _ = core.booking_service.get_booking_for_admin(booking_id=booking_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if booking.duration_minutes is None or booking.duration_minutes <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="У заявки не указана длительность для подбора слота.",
        )

    slots_by_date = core.availability_service.get_available_slots(duration_minutes=booking.duration_minutes)
    _, key_to_slot = _build_slot_hierarchy(slots_by_date)
    if payload.slot_key not in key_to_slot:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Выбранный слот недоступен.")
    selected_start_at, selected_end_at = key_to_slot[payload.slot_key]

    try:
        result = core.booking_service.offer_waitlist_slot_by_admin(
            booking_id=booking_id,
            admin_telegram_user_id=session.user.telegram_user_id,
            slot_start_at_msk_naive=selected_start_at.replace(tzinfo=None),
            slot_end_at_msk_naive=selected_end_at.replace(tzinfo=None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info(
        "Mini App waitlist slot offered by admin: booking_id=%s admin_tg_id=%s slot_key=%s",
        result.booking.id,
        session.user.telegram_user_id,
        payload.slot_key,
    )
    return AdminBookingActionResponse(
        booking_id=result.booking.id,
        status=result.booking.status,
        message="Клиенту отправлено предложение нового слота.",
        admin_public_comment=result.booking.admin_public_comment,
        meeting_link=result.booking.meeting_link,
    )


@router.post("/bookings/{booking_id}/waitlist/reject", response_model=AdminBookingActionResponse)
def reject_waitlist_booking(
    booking_id: int,
    payload: AdminDecisionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
) -> AdminBookingActionResponse:
    session, _ = _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    comment_value = payload.admin_public_comment.strip() if payload.admin_public_comment else None
    try:
        result = core.booking_service.reject_waitlist_by_admin(
            booking_id=booking_id,
            admin_telegram_user_id=session.user.telegram_user_id,
            admin_public_comment=comment_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info(
        "Mini App waitlist rejected by admin: booking_id=%s admin_tg_id=%s",
        result.booking.id,
        session.user.telegram_user_id,
    )
    return AdminBookingActionResponse(
        booking_id=result.booking.id,
        status=result.booking.status,
        message="Заявка из листа ожидания отклонена и перенесена в архив.",
        admin_public_comment=result.booking.admin_public_comment,
        meeting_link=result.booking.meeting_link,
    )
