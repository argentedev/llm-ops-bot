# Postmortem 001: invalid model API key

This was a drill, not a real incident. I broke the bot on purpose to see what I would notice and what I would not. Claude suggested the exercise and helped me read the results.

## What I did

On the Ubuntu VM I replaced the model API key in `/etc/llm-ops-bot.env` with an invalid value and restarted the service. Then I sent the bot some messages from my phone. All times are UTC, 2026-11-28.

| Time | What happened |
|---|---|
| 08:05:24 | Service restarted with the invalid key |
| 08:05:45 | First message: error in the journal, `status=401` |
| 08:05:58 | Second message: same error |
| 08:06:23 | Third request (`/summarise`): same error |

I did not note the time at which I put the real key back, so I have no time-to-fix.

## What I saw

- `systemctl status` showed `active (running)` the whole time. The process was fine, but the bot could not do its job.
- The journal, the SQLite log and `/health` agreed: 3 errors, all `status_401`.
- In Telegram I got the same message for every request: "The model API returned an error."
- `/health` showed the number of errors but not their code. To see `status_401` I had to log in to the server.
- The SDK does not retry a 401, so each failure came back fast (263 to 333 ms).

## The problem I found

Nothing told me. If I had not been sending messages, I would only have found out from the next daily summary, about 23 hours later.

## What I changed

Claude suggested two fixes: a simple alert inside the bot, or a separate timer on the server that checks the database. I chose the simple one because the second adds a service, a timer and extra state for a project this size.

I added `bot/alerts.py`. After 3 errors in a row the bot messages me with the last error code, at most once per hour. I tested it locally with an invalid key: messages 1 and 2 returned the error; message 3 returned the alert and the error.

## What I did not do

- I did not test a fourth message to confirm the one-hour limit, and I did not repeat the drill on the server.
- The alert counter lives in memory, so it resets when the service restarts.
- The alert goes through the bot itself, so it cannot tell me the bot is hung.
- I did not write down what I expected to see before breaking it, so I cannot compare it with what happened.

## Still open

- Show the last error code and the number of consecutive errors in `/health`.
- Send a different message to the user for a bad key than for a timeout.
- Send a notice when the bot recovers.

## What I take from it

A running process does not mean a working service, so a failure needs its own signal. Recording the error code from the start made the diagnosis quick.
