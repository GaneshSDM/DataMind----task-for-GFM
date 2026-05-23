"""
groq_client.py
--------------
Groq API client for ARIA intent classifier.
OpenAI-compatible endpoint via httpx.
"""
import time
import logging
import httpx

from config.settings import GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL

logger = logging.getLogger("aria.groq_client")

_RETRYABLE_STATUS = {500, 502, 503, 504}
_RETRYABLE_ERRORS = ("INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED", "rate_limit")


class GroqClient:
    def __init__(self) -> None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        self._api_key = GROQ_API_KEY
        self._model = GROQ_MODEL
        self._url = GROQ_BASE_URL

    def generate(self, prompt: str, retries: int = 2, retry_delay: float = 4.0) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.05,
            "max_tokens": 2048,
        }

        last_exc = None
        for attempt in range(1, retries + 2):
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(self._url, json=body, headers=headers)

                if resp.status_code in _RETRYABLE_STATUS and attempt <= retries:
                    logger.warning("Groq HTTP %s — retrying (attempt %d)", resp.status_code, attempt)
                    time.sleep(retry_delay)
                    continue

                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                if not text.strip():
                    raise ValueError("Groq returned empty content")
                return text

            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                is_retryable = any(e in err_str for e in _RETRYABLE_ERRORS)
                if attempt <= retries and is_retryable:
                    logger.warning("Groq error (retryable): %s — retrying", exc)
                    time.sleep(retry_delay)
                else:
                    raise

        raise last_exc
