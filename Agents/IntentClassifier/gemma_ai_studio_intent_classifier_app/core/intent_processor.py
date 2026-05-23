import json
import re

from core.gemma_client import GemmaClient
from config.settings import STRUCTURED_VIEWS, DOMAIN_TAXONOMY

# 3-intent example: Structured/Data → Both/Reasoning → Structured/Action
# Demonstrates null structured_view on unstructured source and separate conditional Action intent.
_SCHEMA_EXAMPLE = (
    '{"original_query":"...","total_intents":3,"intents":['
    '{"intent_id":1,"description":"Fetch invoice and payment records for order ORD-4589",'
    '"domain":"Finance","sub_domain":"Invoicing","data_source":"Structured",'
    '"structured_view":"Finance_Accounting_Business_View","unstructured_source":null,'
    '"intent_types":["Data"],"requires_data_fetch":true,"requires_reasoning":false,"requires_action":false},'
    '{"intent_id":2,"description":"Retrieve contract discount terms and compare against invoice amount",'
    '"domain":"Sales","sub_domain":"Contract","data_source":"Both",'
    '"structured_view":"Finance_Accounting_Business_View","unstructured_source":"Contract discount terms document",'
    '"intent_types":["Data","Reasoning"],"requires_data_fetch":true,"requires_reasoning":true,"requires_action":false},'
    '{"intent_id":3,"description":"Create invoice correction request because discount was missed",'
    '"domain":"Finance","sub_domain":"Invoicing","data_source":"Structured",'
    '"structured_view":"Finance_Accounting_Business_View","unstructured_source":null,'
    '"intent_types":["Action"],"requires_data_fetch":false,"requires_reasoning":false,"requires_action":true}'
    ']}'
)


class IntentProcessor:
    def __init__(self) -> None:
        self._client = GemmaClient()
        # Pipe-separated views — compact, saves ~80 tokens vs newline list
        self._views = "|".join(STRUCTURED_VIEWS)
        # Compact single-line taxonomy
        self._taxonomy = "|".join(
            f"{d}({','.join(subs)})" for d, subs in DOMAIN_TAXONOMY.items()
        )

    def process(self, query: str) -> dict:
        prompt = self._build_prompt(query)
        raw = self._client.generate(prompt)
        return self._parse(raw)

    def _build_prompt(self, query: str) -> str:
        return (
            "You are ARIA, an enterprise intent analyst. "
            "Decompose the QUERY into the maximum number of atomic intents. "
            "Your entire response must begin with { and end with } — no markdown fences, no text outside the JSON.\n\n"
            f"VIEWS (exact names only; set structured_view=null if none fits):\n{self._views}\n\n"
            f"TAXONOMY:\n{self._taxonomy}\n\n"
            "RULES:\n"
            "Structured=transactional DB records | "
            "Unstructured=docs/contracts/policies/emails/reports/emails/PDFs | "
            "Both=same operation actively reads a structured record AND a document simultaneously — not when a document is only background context\n"
            "Data=fetch/retrieve/list | Reasoning=compare/analyse/validate | Action=create/update/notify/escalate\n"
            "structured_view=null when Unstructured OR no matching view exists — NEVER invent a view name\n"
            "Conditional action ('do X if Y')=separate Action intent | One operation=one intent\n"
            "Multiple documents serving the same analytical step in the same domain=one intent; different domains or purposes=separate intents\n"
            "unstructured_source: brief document type, 5-10 words max (e.g. 'Contract discount terms document')\n"
            "Order intents by execution sequence: Data intents first, Reasoning intents second, Action intents last\n\n"
            f"EXAMPLE OUTPUT:\n{_SCHEMA_EXAMPLE}\n\n"
            f"QUERY: {query}"
        )

    @staticmethod
    def _parse(text: str) -> dict:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(
                f"Model did not return valid JSON.\n\nRaw output (first 400 chars):\n{text[:400]}"
            )
