from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.admin.service import AdminService
from app.web.api.dependencies.auth import get_auth_service
from app.web.api.dependencies.services import MiniAppCoreServices, get_admin_service, get_core_services
from app.web.api.schemas.admin_availability import (
    AdminAvailabilitySettingsResponse,
    AdminCalendarBookingPreviewPayload,
    AdminCalendarDayPayload,
    AdminCalendarOverviewResponse,
    AdminClosedDayPayload,
    AdminClosedDayUpdateRequest,
    AdminMinLeadUpdateRequest,
    AdminOneTimeWindowPayload,
    AdminOneTimeWindowCreateRequest,
    AdminOneTimeWindowDeleteRequest,
    AdminOneTimeWindowDeleteByDateRequest,
    AdminSettingsMessageResponse,
    AdminTimeBlockCreateRequest,
    AdminTimeBlockDeleteRequest,
    AdminTimeBlockPayload,
    AdminWindowSpanPayload,
    AdminWorkingWindowClearRequest,
    AdminWorkingWindowDeleteRequest,
    AdminWorkingWindowPayload,
    AdminWorkingWindowUpsertRequest,
)
from app.web.services.auth import MiniAppAuthService, TelegramInitDataError

router = APIRouter(prefix="/api/miniapp/admin")
logger = logging.getLogger(__name__)


def _parse_one_time_windows(rows: list[dict]) -> list[AdminOneTimeWindowPayload]:
    payload: list[AdminOneTimeWindowPayload] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            payload.append(
                AdminOneTimeWindowPayload(
                    date=datetime.strptime(str(row.get("date", "")), "%Y-%m-%d").date(),
                    start_time=datetime.strptime(str(row.get("start", "")), "%H:%M").time(),
                    end_time=datetime.strptime(str(row.get("end", "")), "%H:%M").time(),
                    comment=row.get("comment"),
                )
            )
        except ValueError:
            continue
    return payload


def _resolve_admin(init_data: str, auth_service: MiniAppAuthService, core: MiniAppCoreServices):
    try:
        session = auth_service.build_session(init_data)
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App authorization failed.",
        ) from exc
    if not session.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin mode required.")
    core.user_service.ensure_user_from_telegram(
        telegram_user_id=session.user.telegram_user_id,
        telegram_username=session.user.username,
        telegram_display_name=session.user.first_name,
    )
    return session


@router.get("/calendar/overview", response_model=AdminCalendarOverviewResponse)
def get_calendar_overview(
    init_data: str = Query(..., min_length=1),
    from_date: Optional[date] = Query(default=None),
    days: int = Query(default=21, ge=1, le=62),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminCalendarOverviewResponse:
    _resolve_admin(init_data, auth_service=auth_service, core=core)
    start_date = from_date or date.today()
    rows = admin_service.get_calendar_overview(start_date=start_date, horizon_days=days)
    items = [
        AdminCalendarDayPayload(
            date=row["date"],
            is_closed=row["is_closed"],
            closed_reason=row["closed_reason"],
            working_windows=[
                AdminWindowSpanPayload(start_time=window["start_time"], end_time=window["end_time"])
                for window in row["working_windows"]
            ],
            time_blocks=[
                AdminTimeBlockPayload(
                    block_id=block["block_id"],
                    date=row["date"],
                    start_time=block["start_time"],
                    end_time=block["end_time"],
                    comment=block["comment"],
                )
                for block in row["time_blocks"]
            ],
            pending_count=row["pending_count"],
            confirmed_count=row["confirmed_count"],
            reschedule_count=row["reschedule_count"],
            bookings_preview=[
                AdminCalendarBookingPreviewPayload(
                    booking_id=preview["booking_id"],
                    topic=preview["topic"],
                    status=preview["status"],
                    slot_start_at=preview["slot_start_at"],
                    slot_end_at=preview["slot_end_at"],
                    client_name=preview["client_name"],
                    client_username=preview["client_username"],
                )
                for preview in row["bookings_preview"]
            ],
        )
        for row in rows
    ]
    logger.info("Mini App admin calendar overview loaded: start=%s days=%s", start_date.isoformat(), days)
    return AdminCalendarOverviewResponse(items=items)


@router.get("/availability/settings", response_model=AdminAvailabilitySettingsResponse)
def get_availability_settings(
    init_data: str = Query(..., min_length=1),
    from_date: Optional[date] = Query(default=None),
    days: int = Query(default=45, ge=1, le=120),
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminAvailabilitySettingsResponse:
    _resolve_admin(init_data, auth_service=auth_service, core=core)
    target_from = from_date or date.today()
    payload = admin_service.get_availability_snapshot(from_date=target_from, days=days)
    return AdminAvailabilitySettingsResponse(
        min_lead_minutes=payload["min_lead_minutes"],
        working_windows=[
            AdminWorkingWindowPayload(
                rule_id=row.id,
                weekday=row.weekday,
                start_time=row.start_time,
                end_time=row.end_time,
            )
            for row in payload["working_windows"]
        ],
        closed_days=[
            AdminClosedDayPayload(date=row.date, reason=row.reason)
            for row in payload["closed_days"]
        ],
        time_blocks=[
            AdminTimeBlockPayload(
                block_id=row.id,
                date=row.date,
                start_time=row.start_time,
                end_time=row.end_time,
                comment=row.comment,
            )
            for row in payload["time_blocks"]
        ],
        one_time_windows=_parse_one_time_windows(payload["one_time_windows"]),
    )


@router.post("/availability/working-windows", response_model=AdminSettingsMessageResponse)
def add_working_window(
    payload: AdminWorkingWindowUpsertRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    admin_service.set_working_window(payload.weekday, payload.start_time, payload.end_time)
    return AdminSettingsMessageResponse(message="Время для встреч сохранено.")


@router.post("/availability/working-windows/clear", response_model=AdminSettingsMessageResponse)
def clear_working_windows(
    payload: AdminWorkingWindowClearRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    deleted = admin_service.clear_working_windows(weekday=payload.weekday)
    return AdminSettingsMessageResponse(message=f"Удалено окон: {deleted}.")


@router.post("/availability/working-windows/remove", response_model=AdminSettingsMessageResponse)
def remove_working_window(
    payload: AdminWorkingWindowDeleteRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    deleted = admin_service.remove_working_window(rule_id=payload.rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Рабочее окно не найдено.")
    return AdminSettingsMessageResponse(message="Рабочее окно удалено.")


@router.post("/availability/min-lead", response_model=AdminSettingsMessageResponse)
def update_min_lead(
    payload: AdminMinLeadUpdateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    admin_service.set_min_lead_minutes(payload.minutes)
    return AdminSettingsMessageResponse(message="Настройка минимального интервала сохранена.")


@router.post("/availability/closed-days/close", response_model=AdminSettingsMessageResponse)
def close_day(
    payload: AdminClosedDayUpdateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    canceled = admin_service.close_day(target_date=payload.date, reason=payload.reason)
    return AdminSettingsMessageResponse(
        message=f"День закрыт. Отменено встреч: {len(canceled)}."
    )


@router.post("/availability/closed-days/reopen", response_model=AdminSettingsMessageResponse)
def reopen_day(
    payload: AdminClosedDayUpdateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    reopened = admin_service.reopen_day(target_date=payload.date)
    if not reopened:
        return AdminSettingsMessageResponse(message="Дата не была закрыта.")
    return AdminSettingsMessageResponse(message="День снова открыт для записи.")


@router.post("/availability/time-blocks", response_model=AdminSettingsMessageResponse)
def add_time_block(
    payload: AdminTimeBlockCreateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    admin_service.add_time_block(
        target_date=payload.date,
        start_at=payload.start_time,
        end_at=payload.end_time,
        comment=payload.comment,
    )
    return AdminSettingsMessageResponse(message="Внутренний блок времени добавлен.")


@router.post("/availability/time-blocks/remove", response_model=AdminSettingsMessageResponse)
def remove_time_block(
    payload: AdminTimeBlockDeleteRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    deleted = admin_service.remove_time_block(payload.block_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Внутренний блок не найден.")
    return AdminSettingsMessageResponse(message="Внутренний блок удален.")


@router.post("/availability/one-time-windows", response_model=AdminSettingsMessageResponse)
def add_one_time_window(
    payload: AdminOneTimeWindowCreateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    admin_service.add_one_time_window(
        target_date=payload.date,
        start_at=payload.start_time,
        end_at=payload.end_time,
        comment=payload.comment,
    )
    return AdminSettingsMessageResponse(message="Разовое окно на дату добавлено.")


@router.post("/availability/one-time-windows/remove-by-date", response_model=AdminSettingsMessageResponse)
def remove_one_time_windows_by_date(
    payload: AdminOneTimeWindowDeleteByDateRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    deleted = admin_service.remove_one_time_windows_by_date(target_date=payload.date)
    return AdminSettingsMessageResponse(message=f"Удалено разовых окон: {deleted}.")


@router.post("/availability/one-time-windows/remove", response_model=AdminSettingsMessageResponse)
def remove_one_time_window(
    payload: AdminOneTimeWindowDeleteRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
    core: MiniAppCoreServices = Depends(get_core_services),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminSettingsMessageResponse:
    _resolve_admin(payload.init_data, auth_service=auth_service, core=core)
    removed = admin_service.remove_one_time_window(
        target_date=payload.date,
        start_at=payload.start_time,
        end_at=payload.end_time,
    )
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Индивидуальное окно не найдено.")
    return AdminSettingsMessageResponse(message="Индивидуальное окно удалено.")
