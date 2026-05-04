from __future__ import annotations

import hashlib
import hmac
import json
import time
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

BOT_TOKEN = "test-miniapp-booking-token"
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
        "query_id": "AAHbooking_query",
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


def _build_client(tmp_path) -> TestClient:
    db_file = tmp_path / "miniapp_stage3.db"
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
    return TestClient(app)


def test_stage3_happy_path_create_draft_save_slots_submit(tmp_path):
    client = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=420900)

    start_response = client.post("/api/miniapp/bookings/new/session", json={"init_data": init_data})
    assert start_response.status_code == 200
    start_payload = start_response.json()
    booking_id = start_payload["booking_id"]

    save_response = client.put(
        f"/api/miniapp/bookings/{booking_id}/details",
        json={
            "init_data": init_data,
            "name": "Тестовый Клиент",
            "topic": "Рабочая консультация",
            "meeting_format": "онлайн",
            "duration_minutes": 30,
            "email": "client@example.com",
            "comment": "Нужна консультация по процессам",
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["status"] == "draft"

    slots_response = client.get(
        "/api/miniapp/bookings/slots",
        params={"init_data": init_data, "duration_minutes": 30},
    )
    assert slots_response.status_code == 200
    slots_payload = slots_response.json()
    assert slots_payload["total_slots"] > 0

    first_day_key = next(iter(slots_payload["time_options_by_day"].keys()))
    slot_key = slots_payload["time_options_by_day"][first_day_key][0]["slot_key"]

    submit_response = client.post(
        f"/api/miniapp/bookings/{booking_id}/submit",
        json={"init_data": init_data, "slot_key": slot_key},
    )
    assert submit_response.status_code == 200
    submit_payload = submit_response.json()
    assert submit_payload["status"] == "pending_decision"
    assert submit_payload["duration_minutes"] == 30


def test_stage3_rejects_invalid_init_data(tmp_path):
    client = _build_client(tmp_path)
    bad_init_data = "user=%7B%7D&auth_date=1&hash=invalid"

    response = client.post("/api/miniapp/bookings/new/session", json={"init_data": bad_init_data})

    assert response.status_code == 401


def test_stage3_requires_phone_when_no_username_and_no_email(tmp_path):
    client = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=420901, username=None)
    start_response = client.post("/api/miniapp/bookings/new/session", json={"init_data": init_data})
    booking_id = start_response.json()["booking_id"]

    response = client.put(
        f"/api/miniapp/bookings/{booking_id}/details",
        json={
            "init_data": init_data,
            "name": "Клиент Без Контакта",
            "topic": "Тема встречи",
            "meeting_format": "онлайн",
            "duration_minutes": 30,
            "email": "",
            "phone": "",
            "comment": "",
        },
    )

    assert response.status_code == 422


def test_stage3_submit_rejects_unknown_slot_key(tmp_path):
    client = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=420902)
    start_payload = client.post("/api/miniapp/bookings/new/session", json={"init_data": init_data}).json()
    booking_id = start_payload["booking_id"]
    client.put(
        f"/api/miniapp/bookings/{booking_id}/details",
        json={
            "init_data": init_data,
            "name": "Клиент",
            "topic": "Тема встречи",
            "meeting_format": "онлайн",
            "duration_minutes": 30,
            "email": "client2@example.com",
            "comment": "",
        },
    )

    response = client.post(
        f"/api/miniapp/bookings/{booking_id}/submit",
        json={"init_data": init_data, "slot_key": "2099-01-01 10:00"},
    )
    assert response.status_code == 409

