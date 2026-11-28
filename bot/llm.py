# llm.py: everything about talking to the model. It sends the text, measures how long it takes,
# and turns any failure into a simple Result with an error code instead of crashing the bot.

# --- Imports ---
import logging  # messages to the journal
import os       # read environment variables
import time     # time.perf_counter() to measure latency
from dataclasses import dataclass  # shortcut to define a class that only holds data (Result)

import anthropic                    # the SDK that calls the model API
from dotenv import load_dotenv      # reads .env for local runs

load_dotenv()  # this file reads LLM_API_KEY when it is imported, so .env must be loaded first
log = logging.getLogger("llm-ops-bot.llm")

# --- Settings ---
MODEL = os.environ.get("LLM_MODEL", "claude-haiku-5-5")  # optional env var, with a default
MAX_OUTPUT_TOKENS = 500   # cap on the answer length (limits cost and long replies)
MAX_INPUT_CHARS = 4000    # longer input is cut (limits cost)
TIMEOUT_SECONDS = 30.0    # give up if the API takes longer than this

# System prompts: the instruction the model gets before my message.
DEFAULT_PROMPT = "You are an operations assistant. Answer briefly and precisely."
SUMMARISE_PROMPT = (
    "You are an ops triage assistant. The user pastes log lines. Reply with: "
    "1) what happened, 2) most likely cause, 3) one next check. Maximum 120 words. "
    "Do not state anything that is not supported by the lines provided."
)

# One client for the whole process, created once at import time.
# If LLM_API_KEY is missing this line raises KeyError and the bot does not start.
# Async version, because the bot is async and must not block while waiting for the model.
# max_retries: the SDK retries 429, 5xx and connection errors with backoff.
# It does NOT retry a 401 (bad key), so that fails right away.
_client = anthropic.AsyncAnthropic(
    api_key=os.environ["LLM_API_KEY"],
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
)


# What ask() always returns, success or not. The other files only read these fields.
@dataclass
class Result:
    text: str            # what the user will see (the answer, or a short error message)
    ok: bool             # True if the model answered
    latency_ms: int      # how long the call took
    in_tokens: int = 0   # tokens sent (default 0 when the call failed)
    out_tokens: int = 0  # tokens received
    error: str = ""      # error code: "timeout", "rate_limit", "connection", "status_<code>"; empty if ok


async def ask(user_text: str, system_prompt: str = DEFAULT_PROMPT) -> Result:
    user_text = user_text[:MAX_INPUT_CHARS]  # cut the input to the limit
    start = time.perf_counter()              # high-precision timer for the latency

    # Small helper to avoid repeating the latency calculation in every return.
    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    try:
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )
    # The order of the excepts matters: Python uses the first one that matches.
    # A timeout is also a connection error, and a rate limit is also a status error,
    # so the specific ones go first and the general ones last.
    except anthropic.APITimeoutError:
        log.error("llm timeout after %ss", TIMEOUT_SECONDS)
        return Result("The model took too long to answer. Try again.", False, elapsed_ms(), error="timeout")
    except anthropic.RateLimitError:  # HTTP 429
        log.error("llm rate limited")
        return Result("The model is rate limited. Try again in a minute.", False, elapsed_ms(), error="rate_limit")
    except anthropic.APIConnectionError:  # could not reach the API at all
        log.error("llm connection error")
        return Result("Could not reach the model API.", False, elapsed_ms(), error="connection")
    except anthropic.APIStatusError as e:  # any other HTTP error (401, 400, 5xx...)
        # Only the status code goes to the log, never the message or the key.
        log.error("llm api error status=%s", e.status_code)
        return Result("The model API returned an error.", False, elapsed_ms(), error=f"status_{e.status_code}")

    # Reached only if the call worked. Token counts only, never the text.
    log.info(
        "llm ok model=%s in_tokens=%s out_tokens=%s",
        MODEL, response.usage.input_tokens, response.usage.output_tokens,
    )
    # The answer comes as a list of blocks; I keep only the text ones and join them.
    text = "".join(b.text for b in response.content if b.type == "text")
    return Result(text, True, elapsed_ms(), response.usage.input_tokens, response.usage.output_tokens)
