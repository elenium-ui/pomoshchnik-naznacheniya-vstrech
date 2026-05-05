from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi.testclient import TestClient

import app.infrastructure.db.models  # noqa: F401
from app.application.services.availability import AvailabilityService
from app.infrastructure.db.base import Base
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.bookings.service import BookingService
from app.modules.users.service import UserService
from app.web.api.app import app
from app.web.api.dependencies.auth import get_auth_service
from app.web.api.dependencies.services import MiniAppCoreServices, get_core_services
from app.web.services.auth import MiniAppAuthService

BOT_TOKEN = "test-miniapp-cabinet-token"
ADMIN_USER_ID = 700100


def _build_init_data(
    *,
    bot_token: str,
    user_id: int,
    first_name: str = "Client",
    username: str | None = "client_user",
    auth_date: int | None = None,
) -> str:
    user_payload = {
        "id": user_id,
        "first_name": first_name,
    }
    if username:
        user_payload["username"] = username

    payload = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAHclient_cabinet_query",
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    payload["hash"] = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return urlencode(payload)


def _build_client(tmp_path) -> tuple[TestClient, MiniAppCoreServices]:
    db_file = tmp_path / "miniapp_stage4.db"
    engine = build_engine(database_url=f"sqlite:///{db_file}", log_level="INFO")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    core = MiniAppCoreServices(
        user_service=UserService(session_factory=session_factory),
        booking_service=BookingService(session_factory=session_factory),
        availability_service=AvailabilityService(session_factory=session_factory),
    )
    app.dependency_overrides[get_auth_service] = lambda: MiniAppAuthService(
        bot_token=BOT_TOKEN,
        admin_user_id=ADMIN_USER_ID,
        max_auth_age_seconds=86_400,
    )
    app.dependency_overrides[get_core_services] = lambda: core
    return TestClient(app), core


def _create_booking_for_user(client: TestClient, init_data: str) -> int:
    response = client.post("/api/miniapp/bookings/new/session", json={"init_data": init_data})
    assert response.status_code == 200
    return response.json()["booking_id"]


def test_stage4_active_history_and_profile_routes(tmp_path):
    client, core = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=520900, username="cabinet_user")
    booking_id = _create_booking_for_user(client, init_data)

    save_response = client.put(
        f"/api/miniapp/bookings/{booking_id}/details",
        json={
            "init_data": init_data,
            "name": "Клиент Тест",
            "topic": "Тема консультации",
            "meeting_format": "онлайн",
            "duration_minutes": 30,
            "email": "client@example.com",
            "phone": "+79990001122",
            "comment": "Комментарий",
        },
    )
    assert save_response.status_code == 200

    user = core.user_service.ensure_user_from_telegram(
        telegram_user_id=520900,
        telegram_username="cabinet_user",
        telegram_display_name="Client",
    )

    core.booking_service.update_booking_fields(
        booking_id=booking_id,
        user_id=user.id,
        status="confirmed",
        slot_start_at=datetime.utcnow() - timedelta(days=2, hours=1),
        slot_end_at=datetime.utcnow() - timedelta(days=2),
    )

    active_response = client.get("/api/miniapp/client/bookings/active", params={"init_data": init_data})
    assert active_response.status_code == 200
    assert active_response.json()["items"] == []

    history_response = client.get("/api/miniapp/client/bookings/history", params={"init_data": init_data})
    assert history_response.status_code == 200
    assert history_response.json()["items"]

    profile_get = client.get("/api/miniapp/client/profile", params={"init_data": init_data})
    assert profile_get.status_code == 200
    assert profile_get.json()["profile"]["email"] == "client@example.com"

    profile_update = client.put(
        "/api/miniapp/client/profile",
        json={
            "init_data": init_data,
            "name": "Новое Имя",
            "email": "new@example.com",
            "phone": "+79990003344",
        },
    )
    assert profile_update.status_code == 200
    assert profile_update.json()["profile"]["name"] == "Новое Имя"


def test_stage4_cancel_and_reschedule_start(tmp_path):
    client, core = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=520901, username="reschedule_user")
    booking_id = _create_booking_for_user(client, init_data)

    save_response = client.put(
        f"/api/miniapp/bookings/{booking_id}/details",
        json={
            "init_data": init_data,
            "name": "Клиент",
            "topic": "Тема",
            "meeting_format": "онлайн",
            "duration_minutes": 30,
            "email": "client@example.com",
        },
    )
    assert save_response.status_code == 200

    user = core.user_service.ensure_user_from_telegram(
        telegram_user_id=520901,
        telegram_username="reschedule_user",
        telegram_display_name="Client",
    )
    core.booking_service.update_booking_fields(
        booking_id=booking_id,
        user_id=user.id,
        status="pending_decision",
        slot_start_at=datetime.utcnow() + timedelta(days=1),
        slot_end_at=datetime.utcnow() + timedelta(days=1, minutes=30),
    )

    reschedule_start = client.post(
        f"/api/miniapp/client/bookings/{booking_id}/reschedule/start",
        json={"init_data": init_data},
    )
    assert reschedule_start.status_code == 200
    assert reschedule_start.json()["available_slots"]["total_slots"] > 0
    first_day_key = next(iter(reschedule_start.json()["available_slots"]["time_options_by_day"].keys()))
    slot_key = reschedule_start.json()["available_slots"]["time_options_by_day"][first_day_key][0]["slot_key"]

    submit_response = client.post(
        f"/api/miniapp/client/bookings/{booking_id}/reschedule/submit",
        json={"init_data": init_data, "slot_key": slot_key},
    )
    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "reschedule_requested"

    cancel_response = client.post(
        f"/api/miniapp/client/bookings/{booking_id}/cancel",
        json={"init_data": init_data},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "canceled_by_user"
