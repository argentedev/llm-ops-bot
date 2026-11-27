import logging
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("llm-ops-bot.llm")

MODEL = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
MAX_OUTPUT_TOKENS = 500
MAX_INPUT_CHARS = 4000
TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = (
    "You are an operations assistant. Answer briefly and precisely. "
    "If the user pastes log lines, summarise what happened, the most likely "
    "cause, and one next check."
)

# max_retries: the SDK retries 429, 5xx and connection errors with backoff.
_client = anthropic.AsyncAnthropic(
    api_key=os.environ["LLM_API_KEY"],
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
)


async def ask(user_text: str) -> str:
    user_text = user_text[:MAX_INPUT_CHARS]
    try:
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
        )
    except anthropic.APITimeoutError:
        log.error("llm timeout after %ss", TIMEOUT_SECONDS)
        return "The model took too long to answer. Try again."
    except anthropic.RateLimitError:
        log.error("llm rate limited")
        return "The model is rate limited. Try again in a minute."
    except anthropic.APIConnectionError:
        log.error("llm connection error")
        return "Could not reach the model API."
    except anthropic.APIStatusError as e:
        log.error("llm api error status=%s", e.status_code)
        return "The model API returned an error."
    log.info(
        "llm ok model=%s in_tokens=%s out_tokens=%s",
        MODEL, response.usage.input_tokens, response.usage.output_tokens,
    )
    return "".join(b.text for b in response.content if b.type == "text")