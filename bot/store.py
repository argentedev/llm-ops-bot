import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("llm-ops-bot.store")

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


def _db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "bot.db"
    return Path(os.environ.get("DB_PATH", default))


@contextmanager
def _db():
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_request(kind, ok, latency_ms, in_tokens, out_tokens, error) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO requests (ts, kind, ok, latency_ms, in_tokens, out_tokens, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, kind, int(ok), latency_ms, in_tokens, out_tokens, error),
            )
    except sqlite3.Error:
        log.exception("could not write request log")


def stats(hours: int = 24) -> dict:
    with _db() as conn:
        total, errors, avg_ms, tok_in, tok_out = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(ok = 0), 0),"
            " AVG(CASE WHEN ok = 1 THEN latency_ms END),"
            " COALESCE(SUM(in_tokens), 0), COALESCE(SUM(out_tokens), 0)"
            " FROM requests WHERE ts >= datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchone()
        last = conn.execute(
            "SELECT ts, ok, latency_ms FROM requests ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "hours": hours, "total": total, "errors": errors, "avg_ms": avg_ms,
        "tok_in": tok_in, "tok_out": tok_out, "last": last,
    }


def format_stats(s: dict) -> str:
    avg = f"{s['avg_ms']:.0f} ms" if s["avg_ms"] is not None else "n/a"
    lines = [
        f"Last {s['hours']} h: {s['total']} requests, {s['errors']} errors",
        f"Average latency (ok only): {avg}",
        f"Tokens: {s['tok_in']} in / {s['tok_out']} out",
    ]
    if s["last"]:
        ts, ok, ms = s["last"]
        lines.append(f"Last request: {ts} UTC, {'ok' if ok else 'error'}, {ms} ms")
    return "\n".join(lines)