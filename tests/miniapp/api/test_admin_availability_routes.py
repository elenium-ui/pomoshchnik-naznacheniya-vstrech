from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from fastapi.testclient import TestClient

import app.infrastructure.db.models  # noqa: F401
from app.application.services.availability import AvailabilityService
from app.infrastructure.db.base import Base
from app.infrastructure.db.session import build_engine, build_session_factory
from app.modules.admin.service import AdminService
from app.modules.bookings.service import BookingService
from app.modules.users.service import UserService
from app.web.api.app import app
from app.web.api.dependencies.auth import get_auth_service
from app.web.api.dependencies.services import MiniAppCoreServices, get_admin_service, get_core_services
from app.web.services.auth import MiniAppAuthService

BOT_TOKEN = "test-miniapp-admin-availability"
ADMIN_USER_ID = 810001


class DummyCalendarClient:
    def create_event(self, _request):
        return "event-test-id"

    def update_event(self, _event_id, _request):
        return None

    def delete_event(self, _event_id):
        return None


def _build_init_data(*, user_id: int, username: str) -> str:
    payload = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHstage6_admin_query",
        "user": json.dumps({"id": user_id, "first_name": "Elena", "username": username}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret_key = hmac.new(key=b"WebAppData", msg=BOT_TOKEN.encode("utf-8"), digestmod=hashlib.sha256).digest()
    payload["hash"] = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return urlencode(payload)


def _build_client(tmp_path) -> tuple[TestClient, MiniAppCoreServices, AdminService]:
    db_file = tmp_path / "miniapp_stage6.db"
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
    admin_service = AdminService(
        session_factory=session_factory,
        google_service_account_file="dummy.json",
        google_calendar_id="calendar@example.com",
    )
    admin_service._calendar_client = DummyCalendarClient()  # noqa: SLF001

    app.dependency_overrides[get_auth_service] = lambda: MiniAppAuthService(
        bot_token=BOT_TOKEN,
        admin_user_id=ADMIN_USER_ID,
        max_auth_age_seconds=86_400,
    )
    app.dependency_overrides[get_core_services] = lambda: core
    app.dependency_overrides[get_admin_service] = lambda: admin_service
    return TestClient(app), core, admin_service


def test_stage6_admin_availability_access_denied_for_client(tmp_path):
    client, _, _ = _build_client(tmp_path)
    client_init_data = _build_init_data(user_id=123456, username="client_user")
    response = client.get("/api/miniapp/admin/calendar/overview", params={"init_data": client_init_data})
    assert response.status_code == 403


def test_stage6_admin_availability_flow(tmp_path):
    client, core, _ = _build_client(tmp_path)
    admin_init_data = _build_init_data(user_id=ADMIN_USER_ID, username="admin_user")
    user_init_data = _build_init_data(user_id=123450, username="client_user")

    start = client.post("/api/miniapp/bookings/new/session", json={"init_data": user_init_data})
    booking_id = start.json()["booking_id"]
    save = client.put(
        f"/api/miniapp/bookings/{booking_id}/details",
        json={
            "init_data": user_init_data,
            "name": "Клиент",
            "topic": "Этап 6 проверка",
            "meeting_format": "онлайн",
            "duration_minutes": 30,
            "email": "client@example.com",
        },
    )
    assert save.status_code == 200

    user = core.user_service.ensure_user_from_telegram(
        telegram_user_id=123450,
        telegram_username="client_user",
        telegram_display_name="Client",
    )
    slot_start = datetime.utcnow() + timedelta(days=1)
    core.booking_service.update_booking_fields(
        booking_id=booking_id,
        user_id=user.id,
        status="pending_decision",
        slot_start_at=slot_start,
        slot_end_at=slot_start + timedelta(minutes=30),
    )

    overview = client.get(
        "/api/miniapp/admin/calendar/overview",
        params={"init_data": admin_init_data, "from_date": date.today().isoformat(), "days": 14},
    )
    assert overview.status_code == 200
    assert len(overview.json()["items"]) == 14

    min_lead = client.post(
        "/api/miniapp/admin/availability/min-lead",
        json={"init_data": admin_init_data, "minutes": 180},
    )
    assert min_lead.status_code == 200

    add_window = client.post(
        "/api/miniapp/admin/availability/working-windows",
        json={
            "init_data": admin_init_data,
            "weekday": 1,
            "start_time": "11:00",
            "end_time": "13:00",
        },
    )
    assert add_window.status_code == 200

    settings_after_window = client.get(
        "/api/miniapp/admin/availability/settings",
        params={"init_data": admin_init_data, "days": 45},
    )
    assert settings_after_window.status_code == 200
    monday_windows = [
        row for row in settings_after_window.json()["working_windows"] if row["weekday"] == 1
    ]
    assert monday_windows
    remove_window = client.post(
        "/api/miniapp/admin/availability/working-windows/remove",
        json={"init_data": admin_init_data, "rule_id": monday_windows[0]["rule_id"]},
    )
    assert remove_window.status_code == 200

    target_date = (date.today() + timedelta(days=2)).isoformat()
    close_day = client.post(
        "/api/miniapp/admin/availability/closed-days/close",
        json={"init_data": admin_init_data, "date": target_date, "reason": "Тест"},
    )
    assert close_day.status_code == 200

    add_block = client.post(
        "/api/miniapp/admin/availability/time-blocks",
        json={
            "init_data": admin_init_data,
            "date": target_date,
            "start_time": "12:00",
            "end_time": "12:30",
            "comment": "internal",
        },
    )
    assert add_block.status_code == 200

    one_time = client.post(
        "/api/miniapp/admin/availability/one-time-windows",
        json={
            "init_data": admin_init_data,
            "date": target_date,
            "start_time": "15:00",
            "end_time": "16:00",
            "comment": "manual window",
        },
    )
    assert one_time.status_code == 200

    settings = client.get(
        "/api/miniapp/admin/availability/settings",
        params={"init_data": admin_init_data, "days": 45},
    )
    assert settings.status_code == 200
    payload = settings.json()
    assert payload["min_lead_minutes"] == 180
    assert isinstance(payload["working_windows"], list)
    assert any(day["date"] == target_date for day in payload["closed_days"])
    assert payload["time_blocks"]
    assert payload["one_time_windows"]

    remove_one_time_single = client.post(
        "/api/miniapp/admin/availability/one-time-windows/remove",
        json={
            "init_data": admin_init_data,
            "date": target_date,
            "start_time": "15:00",
            "end_time": "16:00",
        },
    )
    assert remove_one_time_single.status_code == 200

    block_id = payload["time_blocks"][0]["block_id"]
    remove_block = client.post(
        "/api/miniapp/admin/availability/time-blocks/remove",
        json={"init_data": admin_init_data, "block_id": block_id},
    )
    assert remove_block.status_code == 200

    reopen_day = client.post(
        "/api/miniapp/admin/availability/closed-days/reopen",
        json={"init_data": admin_init_data, "date": target_date},
    )
    assert reopen_day.status_code == 200

    remove_one_time = client.post(
        "/api/miniapp/admin/availability/one-time-windows/remove-by-date",
        json={"init_data": admin_init_data, "date": target_date},
    )
    assert remove_one_time.status_code == 200
