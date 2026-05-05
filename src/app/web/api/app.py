from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.web.api.routers.admin_availability import router as admin_availability_router
from app.web.api.routers.admin_cabinet import router as admin_cabinet_router
from app.web.api.routers.auth import router as auth_router
from app.web.api.routers.booking_flow import router as booking_flow_router
from app.web.api.routers.client_cabinet import router as client_cabinet_router
from app.web.api.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="ER Meet Mini App API",
        version="0.1.0-stage1",
        description="Stage 1 API shell for Telegram Mini App.",
    )
    # Stage local dev: allow Mini App frontend to call API from localhost dev server.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router, tags=["auth"])
    app.include_router(booking_flow_router, tags=["bookings"])
    app.include_router(client_cabinet_router, tags=["client-cabinet"])
    app.include_router(admin_cabinet_router, tags=["admin-cabinet"])
    app.include_router(admin_availability_router, tags=["admin-availability"])
    app.include_router(health_router, tags=["system"])
    return app


app = create_app()
