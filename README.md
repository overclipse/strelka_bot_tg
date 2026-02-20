# strelka_bot_tg

Telegram-бот для проверки баланса карты Стрелка через API:
`https://strelkacard.ru/api/cards/status/`

Также поднимается web service-заглушка (FastAPI).

## Возможности

- Сохраняет номер карты в SQLite (`user_id -> card_number`)
- Показывает баланс и статус карты по команде `/balance`
- Поднимает HTTP-заглушку:
  - `GET /`
  - `GET /health`

## .env

Скопируйте пример:

```bash
cp .env.example .env
```

Поля:

- `TELEGRAM_BOT_TOKEN` — токен от BotFather
- `WEB_HOST` — хост web-сервиса (по умолчанию `0.0.0.0`)
- `WEB_PORT` — порт web-сервиса (по умолчанию `8080`)
- `SQLITE_PATH` — путь к SQLite-файлу (по умолчанию `./data/bot.db`)

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполните TELEGRAM_BOT_TOKEN в .env
python bot.py
```

## Команды бота

- `/start` — помощь
- `/setcard <номер_карты>` — сохранить номер карты в SQLite
- `/card` — показать сохраненный номер
- `/balance` — показать баланс и статус карты

## Docker

Сборка образа:

```bash
docker build -t strelka-bot:latest .
```

Запуск контейнера:

```bash
docker run --name strelka-bot \
  --env-file .env \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  strelka-bot:latest
```

Проверка web-заглушки:

```bash
curl http://localhost:8080/health
```
