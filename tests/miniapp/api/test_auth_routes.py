from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from app.web.api.app import app
from app.web.api.dependencies.auth import get_auth_service
from app.web.services.auth import MiniAppAuthService

BOT_TOKEN = "test-miniapp-bot-token"
ADMIN_USER_ID = 999001


def _build_init_data(
    *,
    bot_token: str,
    user_id: int,
    first_name: str = "Test",
    auth_date: int | None = None,
) -> str:
    payload = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAHtest_query",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": first_name,
                "username": "miniapp_user",
            },
            separators=(",", ":"),
        ),
    }

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    payload_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    payload["hash"] = payload_hash
    return urlencode(payload)


def _client() -> TestClient:
    app.dependency_overrides[get_auth_service] = lambda: MiniAppAuthService(
        bot_token=BOT_TOKEN,
        admin_user_id=ADMIN_USER_ID,
        max_auth_age_seconds=86_400,
    )
    return TestClient(app)


def test_auth_session_rejects_invalid_signature():
    client = _client()
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=12345) + "broken"

    response = client.post("/api/miniapp/auth/session", json={"init_data": init_data})

    assert response.status_code == 401


def test_auth_session_admin_receives_both_modes():
    client = _client()
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=ADMIN_USER_ID)

    response = client.post("/api/miniapp/auth/session", json={"init_data": init_data})

    assert response.status_code == 200
    payload = response.json()
    assert payload["access"]["is_admin"] is True
    assert payload["access"]["default_mode"] == "admin"
    assert payload["access"]["available_modes"] == ["client", "admin"]


def test_auth_session_non_admin_receives_client_mode_only():
    client = _client()
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=420001)

    response = client.post("/api/miniapp/auth/session", json={"init_data": init_data})

    assert response.status_code == 200
    payload = response.json()
    assert payload["access"]["is_admin"] is False
    assert payload["access"]["default_mode"] == "client"
    assert payload["access"]["available_modes"] == ["client"]


def test_switch_mode_denies_non_admin_to_admin_mode():
    client = _client()
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=420001)

    response = client.post(
        "/api/miniapp/auth/mode",
        json={"init_data": init_data, "mode": "admin"},
    )

    assert response.status_code == 403


def test_switch_mode_allows_admin_to_client_mode():
    client = _client()
    init_data = _build_init_data(bot_token=BOT_TOKEN, user_id=ADMIN_USER_ID)

    response = client.post(
        "/api/miniapp/auth/mode",
        json={"init_data": init_data, "mode": "client"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access"]["current_mode"] == "client"

