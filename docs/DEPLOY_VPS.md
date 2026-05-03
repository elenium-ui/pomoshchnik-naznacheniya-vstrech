# Deploy на VPS (HTTPS webhook)

Документ для прод-развертывания бота на VPS в Docker с `HTTPS webhook`.

## 1. Что должно быть заранее

- сервер с Docker и Docker Compose;
- доступ по SSH;
- домен/поддомен, указывающий на IP сервера;
- открытые порты `80` и `443`.

## 2. Какие данные нужно подготовить

Заполните на сервере файл `.env.production` (по шаблону `.env.production.example`):

- `BOT_TOKEN`
- `ADMIN_USER_ID`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `DATABASE_URL`
- `TELEGRAM_WEBHOOK_BASE_URL`
- `TELEGRAM_WEBHOOK_SECRET`

Рекомендация для `TELEGRAM_WEBHOOK_SECRET`:

```bash
openssl rand -hex 32
```

## 3. Подготовка каталога на сервере

```bash
sudo mkdir -p /opt/meeting-booking-bot
sudo chown -R $USER:$USER /opt/meeting-booking-bot
```

Скопируйте проект в `/opt/meeting-booking-bot`.

## 4. Настройка Caddy

Откройте конфиг:

```bash
sudo nano /etc/caddy/Caddyfile
```

Добавьте блок (замените домен):

```caddyfile
bot.example.com {
    encode zstd gzip
    handle /telegram/webhook* {
        reverse_proxy 127.0.0.1:18080
    }
    handle /health* {
        reverse_proxy 127.0.0.1:18080
    }
    handle {
        respond 404
    }
}
```

Проверка и перезапуск:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 5. Запуск production-контейнера

В каталоге проекта на сервере:

```bash
cp .env.production.example .env.production
mkdir -p data logs
docker compose -f docker-compose.production.yml up -d --build
```

## 6. Проверка

```bash
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs -f meeting-bot
curl -I https://bot.example.com/health
```

Ожидается:

- контейнер `Up`;
- в логах есть запуск webhook-режима;
- `https://<ваш-домен>/health` отвечает `200`.

## 7. Команды эксплуатации

```bash
# Обновить и перезапустить
docker compose -f docker-compose.production.yml up -d --build

# Остановить
docker compose -f docker-compose.production.yml down

# Рестарт
docker compose -f docker-compose.production.yml restart

# Логи
docker compose -f docker-compose.production.yml logs -f meeting-bot
```

## 8. Быстрый rollback

Если после обновления есть проблемы:

1. Верните предыдущую версию кода в каталоге проекта.
2. Выполните:

```bash
docker compose -f docker-compose.production.yml up -d --build
```
