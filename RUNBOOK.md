# Runbook

The commands I use to check and fix the bot on the server. The service is `llm-ops-bot`, the code is in `/opt/llm-ops-bot/app`, and the secrets are in `/etc/llm-ops-bot.env`.

## Check it

```
systemctl status llm-ops-bot --no-pager | head -n 5
sudo journalctl -u llm-ops-bot -n 40 --no-pager | sed -E 's#bot[0-9]+:[A-Za-z0-9_-]+#bot<REDACTED>#g'
```

The `sed` hides anything that looks like a bot token. I do not paste `systemctl status` output without `head`, because it prints the last log lines.

Last requests, with error codes:

```
sudo apt install -y sqlite3
sudo -u botuser sqlite3 /opt/llm-ops-bot/app/bot.db "SELECT ts, kind, ok, latency_ms, error FROM requests ORDER BY id DESC LIMIT 5;"
```

`/health` in Telegram should show the same totals as the database.

## Update

```
sudo -u botuser git -C /opt/llm-ops-bot/app pull
sudo systemctl restart llm-ops-bot
```

If a file in `deploy/` changed, copy it to `/etc/systemd/system/` (check it is not 0 bytes) and run `sudo systemctl daemon-reload` first.

## When I get an alert

The alert says `ALERT: 3 consecutive model API errors (last: <code>)`. I check the last errors with the SQL above and look at the code:

- `status_401`: the API key is invalid or revoked. Replace it (below).
- `rate_limit`, `timeout`, `status_5xx`: usually the provider or a temporary problem. The SDK already retried twice. I check again a bit later.
- `connection`: the server cannot reach the API. I check its network.
- Other `status_<code>`: I check the provider console (balance, model name in `LLM_MODEL`).

To replace the API key: edit `/etc/llm-ops-bot.env` with `sudo nano`, check the lengths with `sudo awk -F= '{print $1 " -> " length($2) " characters"}' /etc/llm-ops-bot.env`, run `sudo systemctl restart llm-ops-bot`, and send the bot a message.

## Telegram token

If the token leaks: send `/revoke` to @BotFather, put the new token in `/etc/llm-ops-bot.env` and in my local `.env`, and restart the service. Open a new terminal after changing `.env`, because an old terminal keeps the old value.

## One process per token

Stop the service (`sudo systemctl stop llm-ops-bot`) before starting the bot anywhere else.
