# Автодеплой из GitHub на VPS (Этап 8)

Этот документ нужен, чтобы настроить автодеплой после каждого `push` в ветку `main`.

## Что уже реализовано в проекте

- workflow: `.github/workflows/deploy-production.yml`
- серверный скрипт: `scripts/deploy-on-server.sh`
- production compose: `docker-compose.production.yml`

## Что нужно сделать вручную в GitHub

Откройте репозиторий на GitHub:

`Settings -> Secrets and variables -> Actions`

### 1) Variables (Repository variables)

Добавьте:

1. `VPS_HOST`  
   Пример: `193.42.125.77`
2. `VPS_SSH_USER`  
   Пример: `elen`
3. `VPS_SSH_PORT`  
   Пример: `22`
4. `VPS_APP_DIR`  
   Пример: `/opt/meeting-booking-bot`
5. `PUBLIC_HEALTHCHECK_URL`  
   Пример: `https://calendar.razumflow.ru/health`

### 2) Secrets (Repository secrets)

Добавьте:

1. `VPS_SSH_PRIVATE_KEY`  
   Содержимое приватного SSH ключа для входа на VPS.
2. `VPS_KNOWN_HOSTS`  
   Хост-ключ сервера, получить локально:

```bash
ssh-keyscan -p 22 193.42.125.77
```

Скопируйте весь вывод и вставьте в секрет.

## Важно по серверу

На сервере в каталоге `VPS_APP_DIR` должен существовать рабочий `.env.production`.

- Workflow не перезаписывает `.env.production`.
- Если `.env.production` отсутствует, скрипт создаст его из `.env` (fallback), но лучше держать явный production-файл.

## Как запустить первый тест

1. Сделайте маленький commit в `main`.
2. Выполните `git push`.
3. На GitHub откройте `Actions -> Deploy Production`.
4. Дождитесь `Success`.

## Как проверить, что автодеплой сработал

1. В логе Actions шаг `Deploy on VPS` должен завершиться успешно.
2. На сервере:

```bash
cd /opt/meeting-booking-bot
sudo docker compose -f docker-compose.production.yml ps
sudo docker compose -f docker-compose.production.yml logs --tail 80
```

3. Проверка health:

```bash
curl -I https://calendar.razumflow.ru/health
```

Ожидается `200 OK`.

## Ручной запуск workflow без push

На GitHub:

`Actions -> Deploy Production -> Run workflow`
