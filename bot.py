import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

import requests
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


BASE_DIR = Path(__file__).resolve().parent
STRELKA_STATUS_URL = "https://strelkacard.ru/api/cards/status/"
DEFAULT_CARD_TYPE_ID = "3ae427a1-0f17-4524-acb1-a3f50090a8f3"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

app_web = FastAPI(title="strelka-bot-web-stub")


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_cards (
                    user_id INTEGER PRIMARY KEY,
                    card_number TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def set_user_card(self, user_id: int, card_number: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_cards (user_id, card_number)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    card_number=excluded.card_number,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, card_number),
            )
            conn.commit()

    def get_user_card(self, user_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT card_number FROM user_cards WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return None
        return row[0]


storage: Storage | None = None


@app_web.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "strelka-bot-web-stub"}


@app_web.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


def parse_status_response(data: Any) -> str:
    if not isinstance(data, dict):
        raise ValueError("Непредвиденный формат ответа API")

    card = data.get("card") if isinstance(data.get("card"), dict) else data
    balance_raw = card.get("balance")
    card_active = card.get("cardactive")
    card_blocked = card.get("cardblocked")
    trips = card.get("numoftrips")

    lines = ["Информация по карте:"]
    if isinstance(balance_raw, (int, float)):
        lines.append(f"Баланс: {balance_raw / 100:.2f} руб. ({int(balance_raw)} коп.)")
    elif balance_raw is not None:
        lines.append(f"Баланс: {balance_raw}")

    if card_active is not None:
        lines.append(f"Карта активна: {'да' if bool(card_active) else 'нет'}")
    if card_blocked is not None:
        lines.append(f"Карта заблокирована: {'да' if bool(card_blocked) else 'нет'}")
    if trips is not None:
        lines.append(f"Поездок: {trips}")

    if len(lines) == 1:
        lines.append("API не вернуло ожидаемые поля (balance/cardactive/cardblocked).")

    return "\n".join(lines)


def fetch_card_status(card_number: str) -> str:
    card_type_id = os.getenv("STRELKA_CARD_TYPE_ID", DEFAULT_CARD_TYPE_ID)
    params = {"cardnum": card_number, "cardtypeid": card_type_id}
    response = requests.get(STRELKA_STATUS_URL, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        error = data.get("error") or data.get("message")
        if error:
            return f"Ошибка API: {error}"

    return parse_status_response(data)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "Привет. Я бот для проверки баланса Стрелки.\n\n"
        "Команды:\n"
        "/setcard <номер_карты> — сохранить номер карты\n"
        "/card — показать сохраненный номер\n"
        "/balance — запросить баланс карты"
    )


async def set_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not context.args:
        await update.message.reply_text("Использование: /setcard <номер_карты>")
        return

    card_number = "".join(context.args).strip()
    if not card_number.isdigit():
        await update.message.reply_text("Номер карты должен содержать только цифры.")
        return

    user = update.effective_user
    if user is None:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    if storage is None:
        await update.message.reply_text("Хранилище не инициализировано.")
        return
    storage.set_user_card(user.id, card_number)
    await update.message.reply_text(f"Карта сохранена: {card_number}")


async def show_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    user = update.effective_user
    if user is None:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    if storage is None:
        await update.message.reply_text("Хранилище не инициализировано.")
        return
    card_number = storage.get_user_card(user.id)
    if not card_number:
        await update.message.reply_text("Карта не сохранена. Сначала выполните /setcard <номер_карты>")
        return

    await update.message.reply_text(f"Сохраненная карта: {card_number}")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    user = update.effective_user
    if user is None:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    if storage is None:
        await update.message.reply_text("Хранилище не инициализировано.")
        return
    card_number = storage.get_user_card(user.id)
    if not card_number:
        await update.message.reply_text("Карта не сохранена. Сначала выполните /setcard <номер_карты>")
        return

    await update.message.reply_text("Запрашиваю данные по карте...")
    try:
        status_text = fetch_card_status(card_number)
    except requests.HTTPError as exc:
        logger.exception("HTTP error while requesting strelka API")
        await update.message.reply_text(f"Ошибка HTTP: {exc}")
        return
    except requests.RequestException as exc:
        logger.exception("Request error while requesting strelka API")
        await update.message.reply_text(f"Ошибка запроса: {exc}")
        return
    except ValueError as exc:
        await update.message.reply_text(f"Ошибка формата ответа: {exc}")
        return

    await update.message.reply_text(status_text)


def run_web_service() -> None:
    web_host = os.getenv("WEB_HOST", "0.0.0.0")
    web_port = int(os.getenv("WEB_PORT", "8080"))
    uvicorn.run(app_web, host=web_host, port=web_port, log_level="info")


def main() -> None:
    global storage
    load_dotenv(BASE_DIR / ".env")
    db_path = Path(os.getenv("SQLITE_PATH", str(BASE_DIR / "data" / "bot.db")))
    storage = Storage(db_path)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Установите TELEGRAM_BOT_TOKEN в .env или переменных окружения")

    web_thread = threading.Thread(target=run_web_service, daemon=True)
    web_thread.start()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setcard", set_card))
    app.add_handler(CommandHandler("card", show_card))
    app.add_handler(CommandHandler("balance", balance))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
