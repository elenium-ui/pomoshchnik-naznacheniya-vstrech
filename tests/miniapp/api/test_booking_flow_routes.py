from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, timedelta
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


def test_stage7_single_active_draft_is_reused_and_can_start_over(tmp_path):
    client = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=420903)

    first_start = client.post("/api/miniapp/bookings/new/session", json={"init_data": init_data})
    assert first_start.status_code == 200
    first_payload = first_start.json()
    first_booking_id = first_payload["booking_id"]
    assert first_payload["has_active_draft"] is False

    second_start = client.post("/api/miniapp/bookings/new/session", json={"init_data": init_data})
    assert second_start.status_code == 200
    second_payload = second_start.json()
    assert second_payload["booking_id"] == first_booking_id
    assert second_payload["has_active_draft"] is True
    assert second_payload["active_draft"]["booking_id"] == first_booking_id

    restart = client.post(
        "/api/miniapp/bookings/new/session",
        json={"init_data": init_data, "start_over": True},
    )
    assert restart.status_code == 200
    restart_payload = restart.json()
    assert restart_payload["booking_id"] != first_booking_id
    assert restart_payload["has_active_draft"] is False


def test_stage7_waitlist_join_from_new_booking(tmp_path):
    client = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=420904, username="waitlist_user")
    start_payload = client.post("/api/miniapp/bookings/new/session", json={"init_data": init_data}).json()
    booking_id = start_payload["booking_id"]
    save = client.put(
        f"/api/miniapp/bookings/{booking_id}/details",
        json={
            "init_data": init_data,
            "name": "Клиент",
            "topic": "Хочу слот на конкретный день",
            "meeting_format": "онлайн",
            "duration_minutes": 30,
            "email": "waitlist@example.com",
            "is_urgent": True,
        },
    )
    assert save.status_code == 200

    waitlist_date = (date.today() + timedelta(days=10)).isoformat()
    waitlist = client.post(
        f"/api/miniapp/bookings/{booking_id}/waitlist",
        json={
            "init_data": init_data,
            "waitlist_date": waitlist_date,
            "waitlist_comment": "Нужна именно эта дата из-за дедлайна."
        },
    )
    assert waitlist.status_code == 200
    waitlist_payload = waitlist.json()
    assert waitlist_payload["status"] == "waitlist"
    assert waitlist_payload["waitlist_date"] == waitlist_date

    active = client.get("/api/miniapp/client/bookings/active", params={"init_data": init_data})
    assert active.status_code == 200
    items = active.json()["items"]
    assert any(item["booking_id"] == booking_id and item["status"] == "waitlist" for item in items)
