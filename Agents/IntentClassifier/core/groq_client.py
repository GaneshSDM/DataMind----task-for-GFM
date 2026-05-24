"""
llm_client.py (formerly groq_client.py)
----------------------------------------
OpenAI-compatible LLM client for ARIA intent classifier.
Works with Groq, vLLM, Ollama, Together, OpenRouter — any OpenAI-compat endpoint.
"""
import time
import logging
import httpx

from config.settings import LLM_API_KEY, LLM_MODEL, LLM_BASE_URL

logger = logging.getLogger("aria.llm_client")

_RETRYABLE_STATUS = {500, 502, 503, 504}
_RETRYABLE_ERRORS = ("INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED", "rate_limit")

_CHAT_URL = LLM_BASE_URL.rstrip("/") + "/chat/completions"


class LLMClient:
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        temperature: float = 0.05,
        max_tokens: int = 2048,
    ) -> None:
        self._api_key    = api_key    or LLM_API_KEY
        self._model      = model      or LLM_MODEL
        self._temperature = temperature
        self._max_tokens  = max_tokens
        if not self._api_key:
            logger.warning("LLM_API_KEY is not set — LLM calls will fail unless provider allows keyless access")

    def generate(self, prompt: str, retries: int = 2, retry_delay: float = 4.0) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model":       self._model,
            "messages":    [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens":  self._max_tokens,
        }

        last_exc = None
        for attempt in range(1, retries + 2):
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(_CHAT_URL, json=body, headers=headers)

                if resp.status_code in _RETRYABLE_STATUS and attempt <= retries:
                    logger.warning("LLM HTTP %s — retrying (attempt %d)", resp.status_code, attempt)
                    time.sleep(retry_delay)
                    continue

                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                if not text.strip():
                    raise ValueError("LLM returned empty content")
                return text

            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                is_retryable = any(e in err_str for e in _RETRYABLE_ERRORS)
                if attempt <= retries and is_retryable:
                    logger.warning("LLM error (retryable): %s — retrying", exc)
                    time.sleep(retry_delay)
                else:
                    raise

        raise last_exc


# Backward-compat alias
GroqClient = LLMClient
