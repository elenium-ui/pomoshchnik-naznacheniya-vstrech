from fastapi import FastAPI

from app.web.api.routers.auth import router as auth_router
from app.web.api.routers.booking_flow import router as booking_flow_router
from app.web.api.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="ER Meet Mini App API",
        version="0.1.0-stage1",
        description="Stage 1 API shell for Telegram Mini App.",
    )
    app.include_router(auth_router, tags=["auth"])
    app.include_router(booking_flow_router, tags=["bookings"])
    app.include_router(health_router, tags=["system"])
    return app


app = create_app()
