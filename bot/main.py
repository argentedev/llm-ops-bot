import logging
import os
import time
import store, llm
import alerts

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters,
)
from llm import SUMMARISE_PROMPT, DEFAULT_PROMPT, ask

load_dotenv()
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
# These HTTP loggers print request URLs; the Telegram URL contains the bot token.
for name in ("httpx", "httpx2"):
    logging.getLogger(name).setLevel(logging.WARNING)
log = logging.getLogger("llm-ops-bot")

ALLOWED = filters.User(user_id=int(os.environ["ALLOWED_USER_ID"]))
STARTED = time.monotonic()


async def _answer(update, context, kind, text, system_prompt=DEFAULT_PROMPT) -> None:
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    result = await ask(text, system_prompt)
    store.log_request(
        kind, result.ok, result.latency_ms, result.in_tokens, result.out_tokens, result.error
    )
    alert = alerts.register(result.ok, result.error)
    if alert:
        await update.message.reply_text(alert)
    await update.message.reply_text(result.text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Bot is running. Commands: /health, /summarise <log lines>")


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uptime_min = int((time.monotonic() - STARTED) / 60)
    text = f"Uptime: {uptime_min} min\n" + store.format_stats(store.stats(24))
    await update.message.reply_text(text)


async def summarise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parts = update.message.text.split(None, 1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /summarise <paste log lines>")
        return
    await _answer(update, context, "summarise", parts[1], SUMMARISE_PROMPT)


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update, context, "chat", update.message.text)


async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("rejected message from user_id=%s", user.id if user else None)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start, filters=ALLOWED))
    app.add_handler(CommandHandler("health", health, filters=ALLOWED))
    app.add_handler(CommandHandler("summarise", summarise, filters=ALLOWED))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ALLOWED, chat))
    # Group 1: runs only for messages that did not match anything above.
    app.add_handler(MessageHandler(filters.ALL & ~ALLOWED, deny), group=1)
    app.run_polling()


if __name__ == "__main__":
    main()