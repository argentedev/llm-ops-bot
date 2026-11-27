import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot

import store

load_dotenv()


async def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["ALLOWED_USER_ID"])
    text = "Daily digest\n" + store.format_stats(store.stats(24))
    async with Bot(token) as bot:
        await bot.send_message(chat_id=chat_id, text=text)
    print("digest sent")


if __name__ == "__main__":
    asyncio.run(main())