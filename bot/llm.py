import logging
import os
import time
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("llm-ops-bot.llm")

MODEL = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
MAX_OUTPUT_TOKENS = 500
MAX_INPUT_CHARS = 4000
TIMEOUT_SECONDS = 30.0

DEFAULT_PROMPT = "You are an operations assistant. Answer briefly and precisely."
SUMMARISE_PROMPT = (
    "You are an ops triage assistant. The user pastes log lines. Reply with: "
    "1) what happened, 2) most likely cause, 3) one next check. Maximum 120 words. "
    "Do not state anything that is not supported by the lines provided."
)

# max_retries: the SDK retries 429, 5xx and connection errors with backoff.
_client = anthropic.AsyncAnthropic(
    api_key=os.environ["LLM_API_KEY"],
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
)


@dataclass
class Result:
    text: str
    ok: bool
    latency_ms: int
    in_tokens: int = 0
    out_tokens: int = 0
    error: str = ""


async def ask(user_text: str, system_prompt: str = DEFAULT_PROMPT) -> Result:
    user_text = user_text[:MAX_INPUT_CHARS]
    start = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    try:
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )
    except anthropic.APITimeoutError:
        log.error("llm timeout after %ss", TIMEOUT_SECONDS)
        return Result("The model took too long to answer. Try again.", False, elapsed_ms(), error="timeout")
    except anthropic.RateLimitError:
        log.error("llm rate limited")
        return Result("The model is rate limited. Try again in a minute.", False, elapsed_ms(), error="rate_limit")
    except anthropic.APIConnectionError:
        log.error("llm connection error")
        return Result("Could not reach the model API.", False, elapsed_ms(), error="connection")
    except anthropic.APIStatusError as e:
        log.error("llm api error status=%s", e.status_code)
        return Result("The model API returned an error.", False, elapsed_ms(), error=f"status_{e.status_code}")

    log.info(
        "llm ok model=%s in_tokens=%s out_tokens=%s",
        MODEL, response.usage.input_tokens, response.usage.output_tokens,
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return Result(text, True, elapsed_ms(), response.usage.input_tokens, response.usage.output_tokens)