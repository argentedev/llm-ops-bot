# alerts.py: decides when to warn me that the model API keeps failing.
# main.py calls register() after every request. The counter lives in memory,
# so it resets to 0 whenever the service restarts.

import time  # time.monotonic(): a clock that does not jump if the system time changes

THRESHOLD = 3            # consecutive errors before alerting
COOLDOWN_SECONDS = 3600  # at most one alert per hour

# Module-level state: these two variables keep their value between calls.
_consecutive = 0    # errors in a row right now
_last_alert = None  # monotonic time of last alert; None = never


# ok / error come from the Result of the model call (llm.py).
# Returns the alert text when I must be warned, otherwise None.
# "str | None" in the hint means "either a string or None".
def register(ok: bool, error: str) -> str | None:
    """Record one request outcome. Return alert text if an alert must be sent, else None."""
    # "global" is needed because I assign to these variables inside the function.
    global _consecutive, _last_alert
    if ok:
        _consecutive = 0  # any success breaks the streak
        return None
    _consecutive += 1
    now = time.monotonic()
    # Alert only if the streak reached the threshold AND (no alert yet OR the cooldown has passed).
    # Without the cooldown I would get a message for every failed request after the 3rd.
    if _consecutive >= THRESHOLD and (
        _last_alert is None or now - _last_alert >= COOLDOWN_SECONDS
    ):
        _last_alert = now
        return (
            f"ALERT: {_consecutive} consecutive model API errors "
            f"(last: {error}). Check /health and journalctl -u llm-ops-bot."
        )
    return None  # below the threshold, or still inside the cooldown
