# Changelog

The order in which I built it. These are milestones, not tagged releases.

## 4. Alert on repeated errors
- Added `bot/alerts.py`. After 3 model API errors in a row the bot messages me with the last error code, at most once per hour.
- Tested locally with an invalid API key: messages 1 and 2 returned the error; message 3 returned the alert and the error.
- Not tested: a fourth message in the same run, and repeating the test on the server.

## 3. Request log, /health and daily summary
- Added a SQLite request log (no message text), `/health`, `/summarise` and a daily summary sent by a systemd timer.
- The model call now returns the error type (`timeout`, `rate_limit`, `connection`, `status_<code>`) and has limits: 500 output tokens, 4000 input characters, 30 s timeout, 2 retries.
- Tested: `/health` matches a SQL query on the database.

## 2. Running on a server
- Added a systemd service for the bot, running as a user with no shell.
- Basic setup on the VM: SSH keys only, no root login, firewall allowing only SSH, automatic security updates.
- Fixed the bot token showing in the logs.
- Tested: `kill -9` and a reboot.

## 1. The bot
- Telegram bot with polling, only my user ID allowed, model call through the Anthropic SDK, settings in `.env`.
