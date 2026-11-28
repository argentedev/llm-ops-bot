# store.py: the request log. Every call to the model is saved as one row in a SQLite file.
# Only metadata is saved (time, type, ok/error, latency, tokens, error code), never the message text.
# /health and the daily digest read their numbers from here.

# --- Imports ---
import logging
import os
import sqlite3                           # SQLite is built into Python, no install needed
from contextlib import contextmanager    # lets me write the "open, use, close" pattern as a function
from datetime import datetime, timezone  # to get the current time in UTC
from pathlib import Path                 # file paths that work on Windows and Linux

log = logging.getLogger("llm-ops-bot.store")

# Table definition. "IF NOT EXISTS" means it is created the first time and left alone after that.
SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,            -- UTC, 'YYYY-MM-DD HH:MM:SS'
    kind TEXT NOT NULL,          -- 'chat' | 'summarise'
    ok INTEGER NOT NULL,         -- 1 ok, 0 error
    latency_ms INTEGER NOT NULL,
    in_tokens INTEGER NOT NULL DEFAULT 0,
    out_tokens INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
)
"""


# Where the database file lives. Default: bot.db in the repo root (this file is in bot/, so two levels up).
# DB_PATH in the environment overrides it. *.db is in .gitignore so it never gets committed.
def _db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "bot.db"
    return Path(os.environ.get("DB_PATH", default))


# Opens a connection, makes sure the table exists, hands it to the caller ("with _db() as conn"),
# then saves the changes and closes the connection, even if something fails in the middle.
# I open a new connection each time because the traffic is tiny.
@contextmanager
def _db():
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(SCHEMA)
        yield conn       # the code inside the "with" block runs here
        conn.commit()    # save the changes if nothing failed
    finally:
        conn.close()     # always close


# Saves one row. Called by main.py after every model call.
def log_request(kind, ok, latency_ms, in_tokens, out_tokens, error) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")  # UTC, same format as the table comment
    try:
        with _db() as conn:
            # The ? are placeholders: the values are passed separately, which avoids quoting problems and SQL injection.
            conn.execute(
                "INSERT INTO requests (ts, kind, ok, latency_ms, in_tokens, out_tokens, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, kind, int(ok), latency_ms, in_tokens, out_tokens, error),  # int(ok): SQLite stores True/False as 1/0
            )
    except sqlite3.Error:
        # If the database fails I only log it. The user still gets the answer; losing a log row is not worth breaking the bot.
        log.exception("could not write request log")


# Numbers for the last N hours, returned as a dictionary. Used by /health and digest.py.
def stats(hours: int = 24) -> dict:
    with _db() as conn:
        # One query, five numbers:
        #   COUNT(*)                           -> total requests
        #   SUM(ok = 0)                        -> how many were errors (COALESCE turns "no rows" NULL into 0)
        #   AVG(CASE WHEN ok = 1 ...)          -> average latency over successful requests only
        #   SUM(in_tokens), SUM(out_tokens)    -> total tokens
        # datetime('now', '-24 hours') is the cutoff; comparing the text works because the format is YYYY-MM-DD HH:MM:SS.
        total, errors, avg_ms, tok_in, tok_out = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(ok = 0), 0),"
            " AVG(CASE WHEN ok = 1 THEN latency_ms END),"
            " COALESCE(SUM(in_tokens), 0), COALESCE(SUM(out_tokens), 0)"
            " FROM requests WHERE ts >= datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchone()
        # The most recent request overall (not limited to the window). None if the table is empty.
        last = conn.execute(
            "SELECT ts, ok, latency_ms FROM requests ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "hours": hours, "total": total, "errors": errors, "avg_ms": avg_ms,
        "tok_in": tok_in, "tok_out": tok_out, "last": last,
    }


# Turns the dictionary from stats() into the text I see in Telegram.
def format_stats(s: dict) -> str:
    # avg_ms is None when there were no successful requests in the window.
    avg = f"{s['avg_ms']:.0f} ms" if s["avg_ms"] is not None else "n/a"
    lines = [
        f"Last {s['hours']} h: {s['total']} requests, {s['errors']} errors",
        f"Average latency (ok only): {avg}",
        f"Tokens: {s['tok_in']} in / {s['tok_out']} out",
    ]
    if s["last"]:  # skip this line if there are no requests yet
        ts, ok, ms = s["last"]
        lines.append(f"Last request: {ts} UTC, {'ok' if ok else 'error'}, {ms} ms")
    return "\n".join(lines)
