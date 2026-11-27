import logging
import os


from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters,
)
from llm import ask
from telegram.constants import ChatAction

load_dotenv()
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("llm-ops-bot")

ALLOWED = filters.User(user_id=int(os.environ["ALLOWED_USER_ID"]))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Bot is running.")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    reply = await ask(update.message.text)
    await update.message.reply_text(reply)


async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("rejected message from user_id=%s", user.id if user else None)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start, filters=ALLOWED))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ALLOWED, chat))
    # Group 1: runs only for messages that did not match anything above.
    app.add_handler(MessageHandler(filters.ALL & ~ALLOWED, deny), group=1)
    app.run_polling()


if __name__ == "__main__":
    main()