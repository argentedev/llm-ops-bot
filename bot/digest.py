# digest.py: sends me the daily summary in Telegram. It is NOT part of the running bot.
# A systemd timer (llm-ops-digest.timer) starts it once a day, it sends one message and exits.

import asyncio  # needed to run an async function from normal code
import os

from dotenv import load_dotenv  # reads .env for local runs (on the server systemd provides the variables)
from telegram import Bot        # the low-level Telegram client, enough to send one message

import store  # my SQLite module, for the same stats that /health shows

load_dotenv()


async def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["ALLOWED_USER_ID"])  # my chat with the bot has the same ID as my user ID
    text = "Daily digest\n" + store.format_stats(store.stats(24))
    # "async with" opens the connection and closes it properly when the block ends.
    async with Bot(token) as bot:
        await bot.send_message(chat_id=chat_id, text=text)
    # Shows up in the journal, so I can check with journalctl that it ran.
    print("digest sent")


# This script only sends (it never polls for updates), so it does not conflict with the running bot
# even though both use the same token.
if __name__ == "__main__":
    asyncio.run(main())  # starts the async code and waits until it finishes
