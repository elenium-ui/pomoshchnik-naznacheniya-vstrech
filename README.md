# Запись на встречу — Stage 10

Реализованы этапы 5-10 и постэтапные доработки:
- показ и выбор слотов пользователем;
- 3-шаговый выбор слота: `неделя -> день -> время`;
- удержание слота и перевод заявки в `pending_decision`;
- уведомление администратора о новой заявке;
- админская карточка заявки;
- inline-кнопки `Подтвердить` и `Отклонить`;
- повторная проверка слота перед подтверждением;
- создание события в Google Calendar;
- добавление гостя по email (если email указан);
- сохранение `calendar_event_id` в заявке;
- освобождение слота при отклонении;
- уведомление пользователя о решении;
- запись истории смены статусов в `status_history`.
- пользовательские карточки заявок с действиями `Отменить` и `Перенести`;
- удаление события из Google Calendar при отмене подтвержденной встречи;
- запрос переноса с выбором нового слота;
- удержание нового слота при переносе;
- сохранение старого слота до решения администратора;
- уведомление администратора о запросе на перенос.
- админ-меню настроек с кнопочными сценариями;
- weekly-окна, min lead, закрытие и повторное открытие даты, внутренние блоки;
- разовые окна на конкретную дату (создание/просмотр/удаление);
- списки закрытых дней и разовых окон;
- поиск/фильтры заявок для админа;
- блокировка/разблокировка пользователя;
- массовая отмена будущих заявок при блокировке;
- удаление будущих событий из Google Calendar при блокировке;
- кнопка `Выбрать другое время` после отмены из-за закрытия дня.
- автоотмена `pending_decision` заявок по TTL;
- освобождение слота после автоотмены;
- уведомление пользователя об автоотмене;
- очистка `status_history` старше 30 дней;
- фоновый планировщик задач с безопасным повторным запуском.
- сквозные интеграционные e2e-проверки ключевых бизнес-сценариев;
- финальная инструкция запуска/перезапуска, чтения логов и смены настроек.
- автоподстановка e-mail в повторной заявке через кнопку `Оставить: <email>`.
- fallback Google Calendar без attendees при `forbiddenForServiceAccounts`.

Ограничение интеграции Google Calendar:
- при работе через service account без Domain-Wide Delegation приглашения attendees могут не отправляться;
- бот в этом случае создает/обновляет событие без attendees, чтобы подтверждение заявки не падало.

## Проверки

```bash
PYTHONPATH=src python -m app.main --check-config
PYTHONPATH=src python -m app.main --health-check
PYTHONPATH=src alembic upgrade head
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src pytest
```

## Установка зависимостей

```bash
pip install ".[test]"
```

## Запуск бота

```bash
PYTHONPATH=src python -m app.main --run-bot
```

Режим запуска задается через `TELEGRAM_DELIVERY_MODE`:
- `polling` (по умолчанию);
- `webhook` (для production через HTTPS).

## Перезапуск бота

1. Остановить текущий процесс в терминале (`Ctrl+C`).
2. Убедиться, что старых процессов нет:
```bash
ps aux | rg "python -m app.main --run-bot"
```
3. Запустить снова:
```bash
PYTHONPATH=src python -m app.main --run-bot
```

## Однократный запуск фоновых задач

```bash
PYTHONPATH=src python -m app.main --run-jobs-once
```

## Настройки через `.env`

Основные параметры:
- `ADMIN_USER_ID` — Telegram user id администратора;
- `GOOGLE_CALENDAR_ID` — id календаря, куда создаются события;
- `GOOGLE_SERVICE_ACCOUNT_FILE` — путь к JSON ключу service account;
- `BOT_TOKEN` — токен Telegram бота;
- `DATABASE_URL` — строка подключения к базе;
- `TIMEZONE` — для MVP `Europe/Moscow`.
- `TELEGRAM_DELIVERY_MODE` — `polling` или `webhook`;
- `TELEGRAM_WEBHOOK_BASE_URL` — например `https://bot.example.com`;
- `TELEGRAM_WEBHOOK_PATH` — путь webhook, по умолчанию `/telegram/webhook`;
- `TELEGRAM_WEBHOOK_SECRET` — секрет заголовка `X-Telegram-Bot-Api-Secret-Token`;
- `TELEGRAM_WEBHOOK_LISTEN_HOST` — host для HTTP сервера webhook (обычно `0.0.0.0`);
- `TELEGRAM_WEBHOOK_LISTEN_PORT` — порт webhook сервера внутри контейнера (обычно `8080`);
- `TELEGRAM_DROP_PENDING_UPDATES_ON_START` — удалять ли отложенные обновления при старте.

Как поменять:
1. Открыть `.env` в корне проекта.
2. Изменить нужные значения.
3. Перезапустить бот.
4. Проверить:
```bash
PYTHONPATH=src python -m app.main --check-config
```

## Логи и диагностика

- основной лог: `logs/app.log`
- лог ошибок: `logs/error.log`

Быстрые команды:
```bash
tail -n 80 logs/app.log
rg -n "ERROR|Traceback|TelegramConflictError" logs/app.log logs/error.log -S
```

## Ручная проверка этапа 10

1. Нажмите `/start`.
2. Пройдите сценарий: пользователь создает заявку -> админ подтверждает.
3. Проверьте событие в Google Calendar.
4. Пройдите сценарий: пользователь отменяет подтвержденную встречу.
5. Пройдите сценарий переноса.
6. Пройдите сценарий закрытия дня с подтвержденной встречей.
7. Пройдите сценарий блокировки пользователя с будущей встречей.
8. Прогоните TTL задачу:
   - `PYTHONPATH=src python -m app.main --run-jobs-once`
9. Убедитесь, что в логах нет критичных ошибок.
10. Проверьте 3-шаговый выбор слота (`неделя -> день -> время`) в новой заявке и переносе.
11. Проверьте в `Админ: настройки` пункт `Закрыть день`.
12. Проверьте в `Админ: настройки` пункт `Открыть день`.
13. Проверьте в `Админ: настройки` пункт `Закрытые дни`.
14. Проверьте в `Админ: настройки` -> `Окна работы` weekly-окна и разовые окна (`создать/удалить/список`).

## Логи

- `logs/app.log` — рабочие события;
- `logs/error.log` — ошибки.

## Production deploy (VPS, HTTPS webhook)

Для production используйте:
- `.env.production.example`
- `docker-compose.production.yml`
- `docs/DEPLOY_VPS.md`
- пример Caddy-конфига: `deploy/Caddyfile.meeting-bot.example`

## CI/CD автодеплой (Этап 8)

- workflow: `.github/workflows/deploy-production.yml`
- deploy-скрипт на сервере: `scripts/deploy-on-server.sh`
- ручная настройка GitHub Variables/Secrets: `docs/AUTO_DEPLOY_GITHUB.md`

## Mini App Stage 1 (shell)

Этап 1 добавляет изолированный каркас Mini App без бизнес-логики:
- backend API shell: `src/app/web/**`;
- frontend shell: `frontend/miniapp/**`;
- mini-app тестовый контур: `tests/miniapp/**`.

### Запуск API shell локально

```bash
PYTHONPATH=src python -m app.web.runtime
```

Проверка:
- `http://localhost:8090/health`
- `http://localhost:8090/api/miniapp/smoke`

### Запуск frontend shell локально

```bash
cd frontend/miniapp
npm install
npm run dev
```

Проверка:
- `http://localhost:5173`
