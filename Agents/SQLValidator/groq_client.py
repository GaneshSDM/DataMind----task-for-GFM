"""
LLM client for SQL Validator Agent.
Uses OpenAI-compatible SDK — provider configured via LLM_API_KEY / LLM_BASE_URL.
"""

import os
import json
import hashlib
import logging
import re

from openai import OpenAI

logger = logging.getLogger(__name__)


class GroqClient:
    """OpenAI-SDK-based LLM client (drop-in replacement for urllib-based client)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ):
        self.api_key  = api_key  or os.getenv("LLM_API_KEY")  or os.getenv("GROQ_API_KEY", "")
        self.model    = model    or os.getenv("LLM_MODEL")     or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.temperature = temperature
        self.max_tokens  = max_tokens
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, system_prompt: str, user_message: str) -> dict:
        """Send a chat completion request and return the parsed response."""
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        )
        choice  = response.choices[0]
        content = choice.message.content
        return {
            "content":      content,
            "model":        response.model,
            "usage":        response.usage.model_dump() if response.usage else {},
            "finish_reason": choice.finish_reason,
        }

    def validate_permissions(
        self, query: str, user_info: dict, schema_context: dict
    ) -> dict:
        """Use LLM to reason about query permissions in natural language."""
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
        raw = result["content"].strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
        return json.loads(raw)

    def generate_synthetic_data(
        self, domain: str, subdomain: str, columns: list, row_count: int = 20
    ) -> list[dict]:
        """Generate realistic synthetic data using LLM."""
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
        raw = result["content"].strip()
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
        return json.loads(raw)


def get_query_fingerprint(query: str) -> str:
    """Return a truncated SHA256 of the normalized query."""
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]
