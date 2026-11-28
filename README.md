# llm-ops-bot

A small Telegram bot that sends my messages to an LLM (Claude) and replies with the answer. I built it to practise running a small service on a Linux server: deploying it, reading logs, and seeing what happens when something breaks.

## What it does

- Plain text: sent to the model, the answer comes back in the chat.
- `/summarise <text>`: summarises the text I paste (for example, log lines).
- `/health`: uptime and the last 24 hours of requests (total, errors, average latency, tokens).
- Only my own Telegram user ID can use it. Messages from anyone else are ignored.
- Each request is saved in a local SQLite file: time, type, ok or error, latency, tokens, error code. The message text is never saved.
- A daily summary is sent to me at 08:00 (Madrid time).
- If the model API fails 3 times in a row, the bot sends me an alert (at most one per hour).

## How I built it

I built this with Claude (Anthropic's AI assistant) as my guide. It helped me plan the structure, drafted parts of the code, and helped me work out what was going wrong when things broke. I ran, deployed and tested everything myself on an Ubuntu Server VM, and the problems listed below happened to me. I also used Claude to help draft these docs.

## Setup

Run locally (Windows PowerShell; on Linux use `cp` and `source venv/bin/activate`):

```
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python bot/main.py
```

Fill in `.env` first. Only one process can poll a bot token at a time, so stop any deployed copy before running locally.

| Variable | Meaning |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `ALLOWED_USER_ID` | My numeric Telegram user ID |
| `LLM_API_KEY` | Anthropic API key |
| `LLM_MODEL` | Optional. Default `claude-haiku-5-5` |
| `DB_PATH` | Optional. Default `<repo>/bot.db` |

Deploy on Ubuntu Server 24.04 (the bot uses polling, so no port needs to be open except SSH):

```
sudo apt update && sudo apt install -y git python3-venv python3-pip
sudo adduser --system --group --home /opt/llm-ops-bot --shell /usr/sbin/nologin botuser
sudo -u botuser git clone https://github.com/argentedev/llm-ops-bot.git /opt/llm-ops-bot/app
sudo -u botuser python3 -m venv /opt/llm-ops-bot/app/venv
sudo -u botuser /opt/llm-ops-bot/app/venv/bin/pip install -r /opt/llm-ops-bot/app/requirements.txt
sudo nano /etc/llm-ops-bot.env        # the three variables, no quotes, no spaces
sudo chown root:root /etc/llm-ops-bot.env && sudo chmod 600 /etc/llm-ops-bot.env
cd /opt/llm-ops-bot/app/deploy
sudo cp llm-ops-bot.service llm-ops-digest.service llm-ops-digest.timer /etc/systemd/system/
wc -c /etc/systemd/system/llm-ops-*    # none of them should be 0 bytes
sudo systemctl daemon-reload
sudo systemctl enable --now llm-ops-bot llm-ops-digest.timer
```

Then send the bot a message and `/health` to check it works.

## Things that went wrong

- **Bot token in the logs.** The HTTP library logs request URLs, and the Telegram URL contains the token. I revoked the token, rotated it, and turned that logging down to warnings only.
- **"Unit is masked".** I had committed the systemd service file empty. systemd treats an empty unit file as masked. I now run `git diff --cached --stat` before every commit.
- **Restart loop.** I left `...` as a placeholder in the server's env file, which crashed the bot at startup. I now check the length of each variable without printing it.
- **A test that did nothing.** I tried to simulate a bad API key by setting a variable in the terminal, but I had started the bot with the editor's run button, which ignores it. Typing the command in the terminal fixed it.

## What I tested

- `kill -9` on the process: systemd restarted it.
- Reboot: the bot started on its own.
- `/health` numbers match a direct SQL query on the database.
- Bad API key: see [docs/postmortem-001.md](docs/postmortem-001.md).

## Limits

- The alert counter lives in memory, so it resets when the service restarts.
- The alert is sent through the bot, so it can't report that the bot itself is hung.
- There are no automated tests. I tested by hand.

More: [RUNBOOK.md](RUNBOOK.md) for the commands I use, [CHANGELOG.md](CHANGELOG.md) for the build order.
