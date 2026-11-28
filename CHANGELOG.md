# Changelog

Milestones in build order. They are not tagged releases.

## Milestone 4: failure alerting

### Added
- `bot/alerts.py`: after 3 consecutive model API errors the bot messages the owner with the last error code, at most once per hour. State is in process memory.

### Changed
- `bot/main.py`: each request outcome is registered with the alerting module; the alert is sent before the error reply.

### Verified
- Logic: five consecutive failures return an alert only on the third; a success resets the counter.
- End to end, locally, with an invalid API key: requests 1 and 2 returned the error only; request 3 returned the alert and the error.

### Not verified
- Fourth request without a new alert (cooldown) in a live run; covered only by the logic test.
- Behaviour after a success with the cooldown expired.
- Repeat of the drill on the deployed host.

## Milestone 3: observability

### Added
- `bot/store.py`: SQLite request log (UTC timestamp, kind, success flag, latency, tokens, error code). Message text is never stored.
- `/health` command: uptime and last-24 h statistics.
- `/summarise <text>` command.
- `bot/digest.py` with `deploy/llm-ops-digest.service` and `deploy/llm-ops-digest.timer`: daily digest at 08:00 Europe/Madrid, `Persistent=true`.

### Changed
- `bot/llm.py`: returns a result object (text, success flag, latency, tokens, error code). Limits: 500 output tokens, 4000 input characters, 30 s timeout, 2 SDK retries. Error codes: `timeout`, `rate_limit`, `connection`, `status_<code>`.

### Verified
- `/health` totals equal a direct SQL query.
- The digest arrives when the service is started by hand and the timer is scheduled.

## Milestone 2: deployment

### Added
- `deploy/llm-ops-bot.service`: runs as `botuser`, `Restart=on-failure`, `RestartSec=5`, `NoNewPrivileges=true`, secrets from `/etc/llm-ops-bot.env`.
- Host hardening: SSH key login only, root login disabled, `ufw` allowing SSH only, unattended security updates.

### Security
- `httpx` and `httpx2` loggers set to WARNING. Request URLs contain the Telegram bot token and were being written to the journal at INFO. The token was revoked and rotated; archived logs were vacuumed.

### Verified
- `kill -9` on the main process: the service restarted with a new PID.
- Reboot: the service came up by itself and is enabled.
- The bot answered from the phone after each test.

## Milestone 1: bot

### Added
- Telegram bot with long polling (`python-telegram-bot`), allowlist by user ID, model call through the Anthropic SDK, configuration through `.env`.
- `.env.example`, pinned `requirements.txt`, `.gitignore` for `.env`, `*.db`, `venv/`, `__pycache__/`.
