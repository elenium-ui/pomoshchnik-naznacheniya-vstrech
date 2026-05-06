#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"

cd "$APP_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed."
  exit 1
fi

echo "==> Rollback: stop current containers"
sudo docker compose -f "$COMPOSE_FILE" down

echo "==> Rollback: restore previous image tags (if available)"
services=(meeting-bot miniapp-api miniapp-frontend meeting-jobs)
for service in "${services[@]}"; do
  prev_tag="${service}:previous"
  if sudo docker image inspect "$prev_tag" >/dev/null 2>&1; then
    echo "Restoring image tag for $service from $prev_tag"
    sudo docker tag "$prev_tag" "$service:latest" || true
  fi
done

echo "==> Rollback: start services"
sudo docker compose -f "$COMPOSE_FILE" up -d

echo "==> Rollback: status"
sudo docker compose -f "$COMPOSE_FILE" ps

echo "==> Rollback completed"
