from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.web.api.schemas.health import HealthResponse, SmokeResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="miniapp-api",
        timestamp_utc=datetime.now(timezone.utc),
    )


@router.get("/api/miniapp/smoke", response_model=SmokeResponse)
def smoke_check() -> SmokeResponse:
    return SmokeResponse(
        status="ok",
        message="Mini App API shell is ready.",
    )
