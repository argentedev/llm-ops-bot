# Runbook

Operational procedures for llm-ops-bot on Ubuntu Server 24.04. Placeholders: `<user>` is the admin account, `<host>` is the server.

**Rule:** never paste tokens, API keys, startup tracebacks or unfiltered `systemctl status` / `journalctl` output anywhere. They can contain secrets (see problem 4 and problem 7).

## 1. Reference

| Item | Value |
|---|---|
| Bot service | `llm-ops-bot.service` (`Restart=on-failure`, `RestartSec=5`) |
| Digest | `llm-ops-digest.service` (oneshot) triggered by `llm-ops-digest.timer`, 08:00 Europe/Madrid, `Persistent=true` |
| Code | `/opt/llm-ops-bot/app` (owned by `botuser`) |
| Secrets | `/etc/llm-ops-bot.env`, `root:root`, mode 600 |
| Database | `/opt/llm-ops-bot/app/bot.db` (metadata only) |
| Service user | `botuser`: no shell, no sudo |
| Firewall | `ufw`: deny incoming, allow outgoing, allow 22/tcp |

## 2. Daily operation

**Status**
```
systemctl status llm-ops-bot --no-pager | head -n 5
systemctl list-timers llm-ops-digest.timer
```

**Logs (always filtered)**
```
sudo journalctl -u llm-ops-bot -n 40 --no-pager | sed -E 's#bot[0-9]+:[A-Za-z0-9_-]+#bot<REDACTED>#g'
```

**Health from Telegram:** send `/health`. It reports uptime and the last 24 h: total requests, errors, average latency (successful requests only), tokens, last request.

**Direct check against the database**
```
sudo apt install -y sqlite3
sudo -u botuser sqlite3 /opt/llm-ops-bot/app/bot.db "SELECT COUNT(*), SUM(ok = 0) FROM requests WHERE ts >= datetime('now','-24 hours');"
```
Expected: same total and error count as `/health`.

**Last requests with error code**
```
sudo -u botuser sqlite3 /opt/llm-ops-bot/app/bot.db "SELECT ts, kind, ok, latency_ms, error FROM requests ORDER BY id DESC LIMIT 5;"
```

**Update the code**
```
sudo -u botuser git -C /opt/llm-ops-bot/app pull
sudo systemctl restart llm-ops-bot
sudo -u botuser git -C /opt/llm-ops-bot/app log --oneline -3
```
If a unit file in `deploy/` changed, copy it to `/etc/systemd/system/`, check it is larger than 0 bytes (`wc -c`) and run `sudo systemctl daemon-reload` before restarting.

**Run the digest on demand**
```
sudo systemctl start llm-ops-digest.service
journalctl -u llm-ops-digest -n 10 --no-pager
```
Expected: the digest arrives in Telegram and the journal shows `digest sent`.

**One process per token.** Stop the service before starting the bot anywhere else, including a workstation: `sudo systemctl stop llm-ops-bot`.

## 3. Alert response

Alert text: `ALERT: N consecutive model API errors (last: <code>). Check /health and journalctl -u llm-ops-bot.`

It is sent after 3 consecutive model API errors, at most once per hour. The counter is in process memory.

1. Read the last errors:
   ```
   sudo -u botuser sqlite3 /opt/llm-ops-bot/app/bot.db "SELECT ts, kind, error FROM requests WHERE ok = 0 ORDER BY id DESC LIMIT 10;"
   ```
2. Act on the error code:

| Code | Meaning | Action |
|---|---|---|
| `status_401` | Invalid or revoked API key | Rotate the key (section 4) |
| `rate_limit` | Provider returned 429 | Check provider usage limits and balance; wait. The SDK already retried twice |
| `timeout` | No answer within 30 s | Check provider status; the next request may succeed |
| `connection` | Cannot reach the provider | Check DNS and outbound 443 from the host |
| `status_5xx` | Provider-side error | Check provider status; the SDK already retried twice |
| other `status_<code>` | Other HTTP error | Check the provider console (billing balance, model name in `LLM_MODEL`) |

3. After the fix, send a plain message. A normal answer ends the incident. There is no recovery notice.

Not covered by the alert: a hung process and a Telegram-side outage (the alert is sent through the bot itself).

## 4. Rotating secrets

**Model API key**
1. Create a new key in the provider console and store it in the password manager.
2. `sudo nano /etc/llm-ops-bot.env`: replace the value of `LLM_API_KEY`.
3. `sudo awk -F= '{print $1 " -> " length($2) " characters"}' /etc/llm-ops-bot.env`: no variable may have the length of a placeholder.
4. `sudo systemctl restart llm-ops-bot`
5. Send a plain message: expect an answer.
6. Revoke the old key.

**Telegram token**
1. In @BotFather send `/revoke` and select the bot. A new token is issued.
2. Store it in the password manager.
3. Replace `TELEGRAM_BOT_TOKEN` in `/etc/llm-ops-bot.env` and in any local `.env`.
4. `sudo systemctl restart llm-ops-bot`

## 5. Host hardening (applied once)

**SSH** (`/etc/ssh/sshd_config.d/00-hardening.conf`; the `00-` prefix matters because the first value found wins):
```
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
```
```
sudo sshd -t
sudo sshd -T | grep -Ei 'passwordauthentication|kbdinteractiveauthentication|permitrootlogin'
sudo systemctl reload ssh
```
Test in a new terminal before closing the old one: key login works; `ssh -o PubkeyAuthentication=no <host>` fails with `Permission denied (publickey)`.

**Firewall**
```
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw enable
```
The bot uses polling, so no inbound port other than SSH is needed.

**Automatic security updates**
```
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
apt-config dump | grep Unattended-Upgrade     # expect APT::Periodic::Unattended-Upgrade "1";
```

## 6. Known problems

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `Permission denied (publickey)` after disabling passwords | The client did not offer a non-default key name | `IdentityFile` and `IdentitiesOnly yes` in `~/.ssh/config` |
| 2 | `Unit llm-ops-bot.service is masked` | The unit file was committed empty (0 bytes); systemd treats an empty unit as masked | Fill the file, commit, pull on the host, copy again, `daemon-reload`. Prevention: `git diff --cached --stat` before every commit |
| 3 | Restart loop, exit status 1, `ValueError` in the journal | `ALLOWED_USER_ID` was the placeholder `...` | Real values in the env file; check lengths with the `awk` command |
| 4 | Bot token present in the journal | `httpx` logs request URLs at INFO and the Telegram URL contains the token | `/revoke` and rotate the token; set `httpx` and `httpx2` loggers to WARNING (the model SDK logs under `httpx2`); `sudo journalctl --rotate && sudo journalctl --vacuum-time=1s` (this wipes all archived logs, not only the bot's) |
| 5 | `git push` rejected (fetch first) | The remote had a commit the local repo lacked (README created by GitHub) | `git pull --rebase origin main`, then push |
| 6 | `fatal: not a git repository` on the host | `git pull` run outside the repo | `sudo -u botuser git -C /opt/llm-ops-bot/app pull` |
| 7 | `telegram.error.InvalidToken` after rotating the token, although `.env` is correct | A stale `TELEGRAM_BOT_TOKEN` in the terminal environment; `load_dotenv()` does not override it. The exception message prints the full token | Close the terminal and open a new one after saving `.env`. Never paste that traceback |
| 8 | A test that overrides an environment variable has no effect | The bot was started with the IDE run button, which builds its own environment | Type the command (`python bot/main.py`) in the terminal where the variable was set |

Check after any change to the journal configuration:
```
sudo journalctl -u llm-ops-bot --since "$(systemctl show -p ActiveEnterTimestamp --value llm-ops-bot)" --no-pager | grep -c "HTTP Request"
```
Expected: `0`. The same command with `llm ok` must be greater than 0, so that the 0 is meaningful.
