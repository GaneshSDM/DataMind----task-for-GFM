import time

from google import genai
from google.genai import types

from config.settings import GEMINI_API_KEY, GEMINI_MODEL

# Errors worth retrying (transient server issues)
_RETRYABLE = ("500", "502", "503", "504", "INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED")


class GemmaClient:
    def __init__(self) -> None:
        self._client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=120_000),  # milliseconds
        )

    def generate(self, prompt: str, retries: int = 2, retry_delay: float = 4.0) -> str:
        last_exc = None
        for attempt in range(1, retries + 2):   # attempts = retries + 1
            try:
                response = self._client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.05,
                        max_output_tokens=2048,
                    ),
                )
                text = response.text if response.text else ""
                if not text.strip():
                    raise ValueError("Model returned an empty response (safety filter or server issue)")
                return text

            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                # Only retry on known transient server errors
                is_retryable = any(code in err_str for code in _RETRYABLE)
                if attempt <= retries and is_retryable:
                    time.sleep(retry_delay)
                else:
                    raise exc

        raise last_exc
