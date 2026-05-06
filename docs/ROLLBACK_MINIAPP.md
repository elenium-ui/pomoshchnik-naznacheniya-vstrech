# Rollback Mini App (Stage 9)

Если после деплоя появились ошибки, откат выполняется на сервере из директории проекта.

## Быстрый откат

```bash
cd /opt/meeting-booking-bot
chmod +x scripts/rollback-on-server.sh
./scripts/rollback-on-server.sh
```

Скрипт:
- останавливает текущие контейнеры;
- поднимает стек заново;
- использует ранее сохраненные теги `*:previous`, если они есть.

## Проверка после отката

```bash
sudo docker compose -f docker-compose.production.yml ps
curl -fsS http://127.0.0.1:18080/health
curl -fsS http://127.0.0.1:18090/health
curl -fsS http://127.0.0.1:15173/
```

## Что смотреть в логах

```bash
sudo docker compose -f docker-compose.production.yml logs --tail 120 meeting-bot
sudo docker compose -f docker-compose.production.yml logs --tail 120 miniapp-api
sudo docker compose -f docker-compose.production.yml logs --tail 120 miniapp-frontend
sudo docker compose -f docker-compose.production.yml logs --tail 120 meeting-jobs
```
