from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.web.api.dependencies.auth import get_auth_service
from app.web.api.dependencies.services import MiniAppCoreServices, get_core_services
from app.web.api.schemas.admin_cabinet import (
    AdminBookingActionResponse,
    AdminBookingItemPayload,
    AdminBookingUserPayload,
    AdminBookingsListResponse,
    AdminDecisionRequest,
    AdminUpdateBookingMetaRequest,
)
from app.web.services.auth import MiniAppAuthService, TelegramInitDataError

router = APIRouter(prefix="/api/miniapp/admin")
logger = logging.getLogger(__name__)


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
        meeting_format=booking.format,
        duration_minutes=booking.duration_minutes,
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
