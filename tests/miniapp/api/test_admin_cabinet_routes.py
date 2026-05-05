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

BOT_TOKEN = "test-miniapp-admin-token"
ADMIN_USER_ID = 700100


class DummyCalendarClient:
    def create_event(self, _request):
        return "event-test-id"

    def update_event(self, _event_id, _request):
        return None

    def delete_event(self, _event_id):
        return None


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
        "query_id": "AAHadmin_cabinet_query",
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
    db_file = tmp_path / "miniapp_stage5.db"
    engine = build_engine(database_url=f"sqlite:///{db_file}", log_level="INFO")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    core = MiniAppCoreServices(
        user_service=UserService(session_factory=session_factory),
        booking_service=BookingService(
            session_factory=session_factory,
            calendar_client=DummyCalendarClient(),
        ),
        availability_service=AvailabilityService(session_factory=session_factory),
    )
    app.dependency_overrides[get_auth_service] = lambda: MiniAppAuthService(
        bot_token=BOT_TOKEN,
        admin_user_id=ADMIN_USER_ID,
        max_auth_age_seconds=86_400,
    )
    app.dependency_overrides[get_core_services] = lambda: core
    return TestClient(app), core


def test_stage5_admin_access_denied_for_client(tmp_path):
    client, _ = _build_client(tmp_path)
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=111111, username="simple_user")
    response = client.get("/api/miniapp/admin/bookings", params={"init_data": init_data})
    assert response.status_code == 403


def test_stage5_admin_list_and_decisions_and_meta(tmp_path):
    client, core = _build_client(tmp_path)
    admin_init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=ADMIN_USER_ID, username="admin_user")
    user_init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=123450, username="client_user")

    def _create_pending_booking(topic: str) -> int:
        start = client.post("/api/miniapp/bookings/new/session", json={"init_data": user_init_data})
        booking_id_local = start.json()["booking_id"]
        save = client.put(
            f"/api/miniapp/bookings/{booking_id_local}/details",
            json={
                "init_data": user_init_data,
                "name": "Клиент",
                "topic": topic,
                "meeting_format": "онлайн",
                "duration_minutes": 30,
                "email": "client@example.com",
            },
        )
        assert save.status_code == 200
        return booking_id_local

    booking_id = _create_pending_booking("Тестовая тема")
    reject_booking_id = _create_pending_booking("Тема на отклонение")
    reschedule_booking_id = _create_pending_booking("Тема на перенос")

    # Move bookings to pending_decision with valid slot for admin actions.
    user = core.user_service.ensure_user_from_telegram(
        telegram_user_id=123450,
        telegram_username="client_user",
        telegram_display_name="Client",
    )
    core.booking_service.update_booking_fields(
        booking_id=booking_id,
        user_id=user.id,
        status="pending_decision",
        slot_start_at=datetime.utcnow() + timedelta(days=1),
        slot_end_at=datetime.utcnow() + timedelta(days=1, minutes=30),
    )
    core.booking_service.update_booking_fields(
        booking_id=reject_booking_id,
        user_id=user.id,
        status="pending_decision",
        slot_start_at=datetime.utcnow() + timedelta(days=2),
        slot_end_at=datetime.utcnow() + timedelta(days=2, minutes=30),
    )
    core.booking_service.update_booking_fields(
        booking_id=reschedule_booking_id,
        user_id=user.id,
        status="confirmed",
        slot_start_at=datetime.utcnow() + timedelta(days=3),
        slot_end_at=datetime.utcnow() + timedelta(days=3, minutes=30),
        calendar_event_id="event-old-slot",
    )
    reschedule_start = client.post(
        f"/api/miniapp/client/bookings/{reschedule_booking_id}/reschedule/start",
        json={"init_data": user_init_data},
    )
    assert reschedule_start.status_code == 200
    first_day_key = next(iter(reschedule_start.json()["available_slots"]["time_options_by_day"].keys()))
    first_slot = reschedule_start.json()["available_slots"]["time_options_by_day"][first_day_key][0]["slot_key"]
    reschedule_submit = client.post(
        f"/api/miniapp/client/bookings/{reschedule_booking_id}/reschedule/submit",
        json={"init_data": user_init_data, "slot_key": first_slot},
    )
    assert reschedule_submit.status_code == 200

    list_response = client.get(
        "/api/miniapp/admin/bookings",
        params={"init_data": admin_init_data, "status_filter": "pending_decision"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"]

    meta_response = client.put(
        f"/api/miniapp/admin/bookings/{booking_id}/meta",
        json={
            "init_data": admin_init_data,
            "admin_public_comment": "Подготовьте документы",
            "meeting_link": "https://meet.google.com/test-link",
        },
    )
    assert meta_response.status_code == 200
    assert meta_response.json()["meeting_link"] == "https://meet.google.com/test-link"

    confirm_response = client.post(
        f"/api/miniapp/admin/bookings/{booking_id}/confirm",
        json={"init_data": admin_init_data},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "confirmed"

    booking_detail = client.get(
        f"/api/miniapp/admin/bookings/{booking_id}",
        params={"init_data": admin_init_data},
    )
    assert booking_detail.status_code == 200
    assert booking_detail.json()["admin_public_comment"] == "Подготовьте документы"

    reject_response = client.post(
        f"/api/miniapp/admin/bookings/{reject_booking_id}/reject",
        json={"init_data": admin_init_data},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    reschedule_confirm_response = client.post(
        f"/api/miniapp/admin/bookings/{reschedule_booking_id}/confirm",
        json={"init_data": admin_init_data},
    )
    assert reschedule_confirm_response.status_code == 200
    assert reschedule_confirm_response.json()["status"] == "confirmed"

    reschedule_booking_detail = client.get(
        f"/api/miniapp/admin/bookings/{reschedule_booking_id}",
        params={"init_data": admin_init_data},
    )
    assert reschedule_booking_detail.status_code == 200
    assert reschedule_booking_detail.json()["requested_new_slot_start_at"] is None
