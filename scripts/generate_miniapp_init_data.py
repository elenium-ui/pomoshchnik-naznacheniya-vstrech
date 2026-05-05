#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode


def read_bot_token(env_path: Path) -> str:
    if not env_path.exists():
        raise RuntimeError(f".env file not found: {env_path}")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("BOT_TOKEN="):
            continue
        token = line.split("=", 1)[1].strip()
        if token:
            return token
    raise RuntimeError("BOT_TOKEN is missing in .env")


def build_init_data(bot_token: str, user_id: int, first_name: str, username: str) -> str:
    payload = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHminiapp_local_debug",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": first_name,
                "username": username,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ),
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local tgInitData for Mini App debug.")
    parser.add_argument("--env", default=".env", help="Path to .env with BOT_TOKEN")
    parser.add_argument("--user-id", type=int, required=True, help="Telegram user id for payload")
    parser.add_argument("--first-name", default="LocalUser", help="First name in payload")
    parser.add_argument("--username", default="local_user", help="Username in payload")
    args = parser.parse_args()

    bot_token = read_bot_token(Path(args.env))
    init_data = build_init_data(
        bot_token=bot_token,
        user_id=args.user_id,
        first_name=args.first_name,
        username=args.username,
    )
    print(init_data)


if __name__ == "__main__":
    main()

