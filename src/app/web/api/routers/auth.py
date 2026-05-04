from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.web.api.dependencies.auth import get_auth_service
from app.web.api.schemas.auth import (
    AuthAccessPayload,
    AuthModeSwitchRequest,
    AuthSessionRequest,
    AuthSessionResponse,
    AuthUserPayload,
)
from app.web.services.auth import AccessDeniedError, MiniAppAuthService, TelegramInitDataError

router = APIRouter(prefix="/api/miniapp/auth")


@router.post("/session", response_model=AuthSessionResponse)
def create_session(
    payload: AuthSessionRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
) -> AuthSessionResponse:
    try:
        session = auth_service.build_session(payload.init_data)
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App authorization failed.",
        ) from exc

    return AuthSessionResponse(
        user=AuthUserPayload(
            telegram_user_id=session.user.telegram_user_id,
            first_name=session.user.first_name,
            last_name=session.user.last_name,
            username=session.user.username,
        ),
        access=AuthAccessPayload(
            is_admin=session.is_admin,
            available_modes=list(session.available_modes),
            default_mode=session.default_mode,
            current_mode=session.default_mode,
        ),
    )


@router.post("/mode", response_model=AuthSessionResponse)
def switch_mode(
    payload: AuthModeSwitchRequest,
    auth_service: MiniAppAuthService = Depends(get_auth_service),
) -> AuthSessionResponse:
    try:
        session = auth_service.build_session(payload.init_data)
        selected_mode = auth_service.validate_mode_access(session, payload.mode)
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App authorization failed.",
        ) from exc
    except AccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for requested mode.",
        ) from exc

    return AuthSessionResponse(
        user=AuthUserPayload(
            telegram_user_id=session.user.telegram_user_id,
            first_name=session.user.first_name,
            last_name=session.user.last_name,
            username=session.user.username,
        ),
        access=AuthAccessPayload(
            is_admin=session.is_admin,
            available_modes=list(session.available_modes),
            default_mode=session.default_mode,
            current_mode=selected_mode,
        ),
    )
