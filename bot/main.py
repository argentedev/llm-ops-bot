# main.py: the bot itself. It listens to Telegram, checks who is writing,
# sends the text to the model and replies. This is the file I run.

# --- Imports ---
import logging  # prints messages with a timestamp; on the server they go to the journal
import os       # read environment variables (token, user ID...)
import time     # time.monotonic() for the uptime counter
import store, llm  # my own modules in bot/ (store = SQLite log; llm is not used by name here, I import what I need from it below)
import alerts   # my own module: counts errors in a row and decides when to alert me

from dotenv import load_dotenv  # reads the .env file into environment variables (local runs only)
from telegram import Update     # type of the object Telegram gives each handler (the incoming message)
from telegram.constants import ChatAction  # lets me show "typing..." while the model thinks
from telegram.ext import (
    Application,     # the bot app: holds the token and the polling loop
    CommandHandler,  # runs a function when someone sends a /command
    ContextTypes,    # type hint for the "context" argument (gives access to context.bot)
    MessageHandler,  # runs a function for normal messages
    filters,         # conditions to decide which messages a handler accepts
)
from llm import SUMMARISE_PROMPT, DEFAULT_PROMPT, ask  # the two system prompts and the function that calls the model

# --- Setup that runs once at startup ---

# Load .env into the environment. It does NOT overwrite variables that already exist,
# so a stale variable in my terminal wins over .env (this bit me once).
# On the server there is no .env: systemd loads /etc/llm-ops-bot.env instead.
load_dotenv()

# Log format: time, level (INFO/ERROR...), which module, message.
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
# These HTTP loggers print request URLs; the Telegram URL contains the bot token.
# Setting them to WARNING keeps the token out of the logs. "httpx2" is the one the model SDK uses.
for name in ("httpx", "httpx2"):
    logging.getLogger(name).setLevel(logging.WARNING)
log = logging.getLogger("llm-ops-bot")  # my own logger for this file

# Filter that accepts messages only from my Telegram user ID.
# int() crashes at startup if the value is not a number (for example the "..." placeholder).
ALLOWED = filters.User(user_id=int(os.environ["ALLOWED_USER_ID"]))

# Moment the bot started. monotonic() is a clock that never jumps if the system time changes.
# Used by /health for the uptime. It starts again from 0 whenever the service restarts.
STARTED = time.monotonic()


# --- Shared helper ---

# Used by both chat and /summarise so the logic lives in one place.
# The leading underscore means "internal, not a Telegram handler".
# update = the incoming message; context = gives access to the bot; kind = label for the log.
async def _answer(update, context, kind, text, system_prompt=DEFAULT_PROMPT) -> None:
    # Show "typing..." in the chat while I wait for the model.
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    # Call the model (llm.py). It always returns a Result, even when it fails.
    result = await ask(text, system_prompt)
    # Save one row in SQLite: metadata only, never the message text.
    store.log_request(
        kind, result.ok, result.latency_ms, result.in_tokens, result.out_tokens, result.error
    )
    # Tell alerts.py how it went. It returns the alert text only on the 3rd error in a row
    # (and at most once per hour), otherwise None.
    alert = alerts.register(result.ok, result.error)
    if alert:
        await update.message.reply_text(alert)  # the alert goes out before the normal reply
    await update.message.reply_text(result.text)  # on errors, result.text is a short error message


# --- Handlers: one function per thing the bot understands ---
# "async def" because the Telegram library runs them concurrently; "await" waits for network calls.
# "update: Update" and "-> None" are only hints for me and the editor; Python does not enforce them.

# /start: just confirms the bot is alive and lists the commands.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Bot is running. Commands: /health, /summarise <log lines>")


# /health: uptime plus the last 24 h of stats from the SQLite log.
async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uptime_min = int((time.monotonic() - STARTED) / 60)
    text = f"Uptime: {uptime_min} min\n" + store.format_stats(store.stats(24))
    await update.message.reply_text(text)


# /summarise <text>: sends the pasted text to the model with the log-triage prompt.
async def summarise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Split once on whitespace: parts[0] is "/summarise", parts[1] is everything after it.
    parts = update.message.text.split(None, 1)
    if len(parts) < 2:  # nothing after the command
        await update.message.reply_text("Usage: /summarise <paste log lines>")
        return  # this does not go to the model, so it is not counted as a request
    await _answer(update, context, "summarise", parts[1], SUMMARISE_PROMPT)


# Any normal text message: goes to the model with the default prompt.
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update, context, "chat", update.message.text)


# Messages from anyone who is not me: no reply, only a warning in the log with their user ID.
async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("rejected message from user_id=%s", user.id if user else None)


# --- Wiring everything together ---
def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]  # KeyError if missing
    app = Application.builder().token(token).build()
    # Each handler only accepts messages that pass the ALLOWED filter.
    app.add_handler(CommandHandler("start", start, filters=ALLOWED))
    app.add_handler(CommandHandler("health", health, filters=ALLOWED))
    app.add_handler(CommandHandler("summarise", summarise, filters=ALLOWED))
    # Text that is not a command (~filters.COMMAND means "not"), from me only.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ALLOWED, chat))
    # Group 1: runs only for messages that did not match anything above.
    app.add_handler(MessageHandler(filters.ALL & ~ALLOWED, deny), group=1)
    # Polling: keeps asking Telegram for new messages. Blocks here until the process is stopped
    # (Ctrl+C locally, SIGTERM from systemd on the server).
    app.run_polling()


# Runs main() only when I start this file directly (python bot/main.py),
# not when another file imports it.
if __name__ == "__main__":
    main()
