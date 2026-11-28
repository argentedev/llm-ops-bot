import time

THRESHOLD = 3            # consecutive errors before alerting
COOLDOWN_SECONDS = 3600  # at most one alert per hour

_consecutive = 0
_last_alert = None  # monotonic time of last alert; None = never


def register(ok: bool, error: str) -> str | None:
    """Record one request outcome. Return alert text if an alert must be sent, else None."""
    global _consecutive, _last_alert
    if ok:
        _consecutive = 0
        return None
    _consecutive += 1
    now = time.monotonic()
    if _consecutive >= THRESHOLD and (
        _last_alert is None or now - _last_alert >= COOLDOWN_SECONDS
    ):
        _last_alert = now
        return (
            f"ALERT: {_consecutive} consecutive model API errors "
            f"(last: {error}). Check /health and journalctl -u llm-ops-bot."
        )
    return None