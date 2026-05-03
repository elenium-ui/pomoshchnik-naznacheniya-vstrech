#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
INTERNAL_HEALTHCHECK_URL="${INTERNAL_HEALTHCHECK_URL:-http://127.0.0.1:18080/health}"
PUBLIC_HEALTHCHECK_URL="${PUBLIC_HEALTHCHECK_URL:-}"
HEALTHCHECK_RETRIES="${HEALTHCHECK_RETRIES:-30}"
HEALTHCHECK_SLEEP_SECONDS="${HEALTHCHECK_SLEEP_SECONDS:-2}"

cd "$APP_DIR"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: Compose file not found: $COMPOSE_FILE"
  exit 1
fi

if [[ ! -f ".env.production" ]]; then
  if [[ -f ".env" ]]; then
    cp .env .env.production
    echo "WARN: .env.production missing, created from .env"
  else
    echo "ERROR: Neither .env.production nor .env found."
    exit 1
  fi
fi

delivery_mode="$(grep -E '^TELEGRAM_DELIVERY_MODE=' .env.production | tail -n1 | cut -d= -f2- || true)"
delivery_mode="$(printf '%s' "${delivery_mode:-polling}" | tr '[:upper:]' '[:lower:]')"
if [[ "$delivery_mode" != "polling" && "$delivery_mode" != "webhook" ]]; then
  delivery_mode="polling"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed."
  exit 1
fi

echo "==> Deploy: docker compose up -d --build"
sudo docker compose -f "$COMPOSE_FILE" up -d --build

echo "==> Deploy: container status"
sudo docker compose -f "$COMPOSE_FILE" ps

if [[ "$delivery_mode" == "webhook" ]]; then
  echo "==> Deploy: mode=webhook, waiting for internal health-check: $INTERNAL_HEALTHCHECK_URL"
  ok=0
  for _ in $(seq 1 "$HEALTHCHECK_RETRIES"); do
    if curl -fsS "$INTERNAL_HEALTHCHECK_URL" >/dev/null; then
      ok=1
      break
    fi
    sleep "$HEALTHCHECK_SLEEP_SECONDS"
  done

  if [[ "$ok" -ne 1 ]]; then
    echo "ERROR: Internal health-check failed: $INTERNAL_HEALTHCHECK_URL"
    echo "==> Recent logs"
    sudo docker compose -f "$COMPOSE_FILE" logs --tail 120
    exit 1
  fi

  if [[ -n "$PUBLIC_HEALTHCHECK_URL" ]]; then
    echo "==> Deploy: checking public health URL: $PUBLIC_HEALTHCHECK_URL"
    curl -fsS "$PUBLIC_HEALTHCHECK_URL" >/dev/null
  fi
else
  echo "==> Deploy: mode=polling, checking running service state"
  if ! sudo docker compose -f "$COMPOSE_FILE" ps --status running --services | grep -qx "meeting-bot"; then
    echo "ERROR: Service meeting-bot is not running."
    echo "==> Recent logs"
    sudo docker compose -f "$COMPOSE_FILE" logs --tail 120
    exit 1
  fi
fi

echo "==> Deploy: success"
