# llm-ops-bot

A single-user Telegram bot that forwards messages to an LLM (Anthropic Claude), built and operated as a small production-style service: systemd-managed, hardened host, request log, daily digest and failure alerting.

The bot's features are deliberately small. The point of the project is the operation around it: deployment, logging without leaking secrets, health reporting, and what happens when the model API fails.

## Features

| Input | Behaviour |
|---|---|
| plain text | Sent to the model; the answer comes back in the chat |
| `/summarise <text>` | Summarises the pasted text (for example, log lines) |
| `/health` | Uptime and the last 24 h of request statistics: total, errors, average latency, tokens, last request |
| `/start` | Start message |

- Only one Telegram user ID (`ALLOWED_USER_ID`) is served. Messages from anyone else are ignored and logged.
- Every model request is recorded in SQLite as metadata only: UTC timestamp, kind, success flag, latency, input and output tokens, error code. Message text is never stored.
- A systemd timer sends a daily digest of the last 24 h at 08:00 Europe/Madrid.
- After 3 consecutive model API errors the bot sends an alert to the owner, at most once per hour.

## Design

- **Long polling** (`getUpdates`): no inbound port, no webhook, no TLS certificate. The host firewall allows SSH only.
- **Limits on the model call:** 500 output tokens, 4000 input characters, 30 s timeout, SDK retries 2 times (429, 5xx and connection errors; not 401).
- **Secrets** live in environment variables only. In production they are in `/etc/llm-ops-bot.env` (root-owned, mode 600, read by systemd). The service runs as an unprivileged user (`botuser`: no shell, no sudo) with `NoNewPrivileges=true`.
- **Logging:** the `httpx` and `httpx2` loggers are set to WARNING, because the Telegram Bot API URL contains the bot token and INFO-level request logging would write it to the journal (see [RUNBOOK.md](RUNBOOK.md), problem 4).
- **Failure model:** an invalid model API key does not crash the process; it produces counted, logged `status_401` errors and, after the third in a row, an alert. See [docs/postmortem-001.md](docs/postmortem-001.md).

## Repository layout

```
bot/
  main.py       Telegram handlers, allowlist, polling loop
  llm.py        Model call: limits, timeout, error classification
  store.py      SQLite request log and statistics
  digest.py     Daily digest, run by a systemd timer
  alerts.py     Consecutive-error alerting
deploy/
  llm-ops-bot.service
  llm-ops-digest.service
  llm-ops-digest.timer
docs/
  postmortem-001.md
.env.example
requirements.txt
RUNBOOK.md
CHANGELOG.md
```

## Configuration

| Variable | Required | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from @BotFather |
| `ALLOWED_USER_ID` | yes | Numeric Telegram user ID that may use the bot |
| `LLM_API_KEY` | yes | Anthropic API key |
| `LLM_MODEL` | no | Model name; default `claude-haiku-5-5` |
| `DB_PATH` | no | SQLite file; default `<repo>/bot.db` |

No quotes, no spaces and no placeholder values. A placeholder such as `...` makes the service exit at startup.

## Run locally

```
python -m venv venv
venv\Scripts\Activate.ps1          # Windows PowerShell; on Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env             # Linux: cp .env.example .env ; then fill in the values
python bot/main.py
```

- Only one process may poll a given bot token. Stop any deployed instance first.
- `load_dotenv()` does not override variables already set in the environment. A stale variable in the terminal wins over `.env`.

## Deploy on Ubuntu Server 24.04

Assumes a host with SSH key login, `ufw` allowing only SSH, and outbound HTTPS. Host hardening steps are in [RUNBOOK.md](RUNBOOK.md).

```
sudo apt update && sudo apt install -y git python3-venv python3-pip
sudo adduser --system --group --home /opt/llm-ops-bot --shell /usr/sbin/nologin botuser
sudo -u botuser git clone https://github.com/argentedev/llm-ops-bot.git /opt/llm-ops-bot/app
sudo -u botuser python3 -m venv /opt/llm-ops-bot/app/venv
sudo -u botuser /opt/llm-ops-bot/app/venv/bin/pip install -r /opt/llm-ops-bot/app/requirements.txt
```

Create the secrets file with an editor (not `echo`, to keep secrets out of shell history):

```
sudo nano /etc/llm-ops-bot.env       # the three required variables, one per line
sudo chown root:root /etc/llm-ops-bot.env
sudo chmod 600 /etc/llm-ops-bot.env
sudo awk -F= '{print $1 " -> " length($2) " characters"}' /etc/llm-ops-bot.env
```

Expected: three variables, none with a length of 3 (the length of the `...` placeholder).

Install and start the units:

```
cd /opt/llm-ops-bot/app/deploy
sudo cp llm-ops-bot.service llm-ops-digest.service llm-ops-digest.timer /etc/systemd/system/
wc -c /etc/systemd/system/llm-ops-*      # every file must be larger than 0
sudo systemctl daemon-reload
sudo systemctl enable --now llm-ops-bot llm-ops-digest.timer
systemctl status llm-ops-bot --no-pager | head -n 5
```

An empty unit file is treated by systemd as masked, hence the `wc -c` check.

Smoke test from Telegram: send a plain message (expect an answer) and `/health` (expect uptime and statistics).

## Verified behaviour

- The service restarts by itself after `kill -9` (new PID within about 6 s) and starts on boot without manual action.
- `/health` totals match a direct SQL query on the database.
- The daily digest timer fires and the digest arrives.
- With an invalid API key every request is logged as `status_401`; the alert is sent on the third consecutive error and not on the following one in the same hour (alert verified locally end to end; see the postmortem for the exact scope).

## Known limitations

- Alert state (counter and cooldown) lives in process memory and resets when the service restarts.
- No recovery notice after an alert.
- The alert depends on the bot itself: it cannot detect a hung process or a Telegram-side outage.
- `/health` does not show the error code; the journal and SQLite do.
- One user, one process.
- No automated test suite. Verification is manual and recorded in [CHANGELOG.md](CHANGELOG.md) and the postmortem.

## Documentation

- [RUNBOOK.md](RUNBOOK.md): operation, alert triage, secret handling, known problems.
- [CHANGELOG.md](CHANGELOG.md): milestones.
- [docs/postmortem-001.md](docs/postmortem-001.md): fault-injection drill with an invalid model API key.
