"""
Groq API client for SQL Validator Agent.
Uses the Groq Chat Completions API for LLM-based validation.
"""

import os
import json
import hashlib
import logging
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
_CHAT_URL = LLM_BASE_URL.rstrip("/") + "/chat/completions"


class GroqClient:
    """Minimal Groq API client — no external dependencies beyond stdlib."""

    def __init__(
        self,
        api_key: str = "",
        model: str = os.getenv("LLM_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")),
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, system_prompt: str, user_message: str) -> dict:
        """Send a chat completion request and return the parsed response."""
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }

        data = json.dumps(payload).encode("utf-8")
        req = Request(_CHAT_URL, data=data, headers=self._headers(), method="POST")

        try:
            with urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            if "error" in body:
                raise RuntimeError(f"Groq API error: {body['error']}")

            choice = body["choices"][0]
            content = choice["message"]["content"]

            return {
                "content": content,
                "model": body.get("model", ""),
                "usage": body.get("usage", {}),
                "finish_reason": choice.get("finish_reason", ""),
            }
        except URLError as e:
            raise RuntimeError(f"Groq API connection failed: {e}")

    def validate_permissions(
        self, query: str, user_info: dict, schema_context: dict
    ) -> str:
        """Use Groq LLM to reason about query permissions in natural language."""
        system = """You are the SQL Validator's reasoning engine. Given a SQL query,
user information, and schema rules, identify:
1. Any columns the user is trying to access that they shouldn't
2. Any missing RLS filters
3. Any date constraint violations
4. Whether the overall query is safe

Be precise. Reference specific column names and rules. Output JSON only."""

        prompt = f"""Analyze this SQL query for security violations.

USER: {json.dumps(user_info, indent=2)}

SCHEMA CONTEXT (allowed columns, RLS rules): {json.dumps(schema_context, indent=2)}

QUERY:
{query}

Return a JSON object with:
- "blocked_columns": [list of columns user cannot access]
- "missing_filters": [list of required WHERE predicates that are missing]
- "date_violations": [list of date constraint violations]
- "verdict": "pass" or "fail"
- "reason": brief explanation
"""
        result = self.chat(system, prompt)
        try:
            return json.loads(result["content"])
        except json.JSONDecodeError:
            # Strip markdown fences if present
            raw = result["content"]
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)

    def generate_synthetic_data(
        self, domain: str, subdomain: str, columns: list, row_count: int = 20
    ) -> list[dict]:
        """Generate realistic synthetic data using Groq LLM."""
        system = """You are a synthetic data generator. Generate realistic, diverse
data for database tables. Return ONLY a JSON array of objects. No explanations.
Each object must have all the specified columns. Use realistic values:
- Names: diverse, real-sounding
- Emails: matching name patterns
- Dates: plausible ranges
- Numbers: realistic ranges
- IDs: sequential integers starting at 1
- Prices/money: realistic decimal values"""

        prompt = f"""Generate {row_count} rows of synthetic data for:

DOMAIN: {domain}
SUBDOMAIN: {subdomain}
COLUMNS: {json.dumps(columns)}

Return a JSON array of {row_count} objects. Each object must have all columns.
Make the data diverse and realistic."""

        result = self.chat(system, prompt)
        raw = result["content"]
        # Strip markdown fences
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)


def get_query_fingerprint(query: str) -> str:
    """Return a truncated SHA256 of the normalized query."""
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]
