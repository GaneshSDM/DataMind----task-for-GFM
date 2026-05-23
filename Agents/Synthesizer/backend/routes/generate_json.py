"""
Generate Sample JSON endpoint.

POST /api/generate-sample-json

Calls the LLM to produce a fresh Sales-domain input payload
(different SQL queries and RAG questions each time), then generates
real 1024-dim embeddings for the RAG questions via Google AI.
"""
import asyncio
import json
import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from google import genai
from google.genai import types

from config import get_settings
from services.embedding_service import generate_embedding

router = APIRouter()

# ── LLM prompt ─────────────────────────────────────────────────────────────────
_GENERATION_PROMPT = """You are generating a test input payload for a Domain Synthesizer Agent App.

DATABASE TABLES AVAILABLE (SELECT only):
• semantic_layer.sales_cancellation
  Columns: order_id, customer_id, product_name, product_category, order_date,
           cancellation_date, cancellation_reason, cancellation_status,
           order_value, refund_amount, refund_status, refund_date,
           cancellation_channel, customer_tier

• semantic_layer.sales_shipment
  Columns: order_id, customer_id, product_name, carrier_name, shipment_date,
           expected_delivery_date, actual_delivery_date, delivery_status,
           on_time_delivery (varchar — values: 'Yes' or 'No'),
           customer_rating (numeric 1-5), shipping_cost, tracking_number

KNOWLEDGE BASE DOCUMENTS:
• Sales_Cancellation_KnowledgeBase.pdf — cancellation policies, refund rules,
  eligibility criteria, retention process, escalation procedures
• Sales_Shipment_KnowledgeBase.pdf — delivery policies, carrier SLAs,
  failed delivery attempts, Return to Origin (RTO) process, post-RTO refund timelines

TASK:
Generate a NEW JSON payload that tests a DIFFERENT analytical scenario than this:
  "Analyse cancellation patterns across product categories and cancellation reasons,
   then evaluate carrier-wise shipment performance and delivery status distribution."

Rules:
1. 3–4 SQL queries — all SELECT, only aggregates (GROUP BY / COUNT / SUM / AVG / ROUND).
2. For on_time_delivery comparisons ALWAYS use:
     LOWER(TRIM(on_time_delivery)) IN ('yes','true','1','y')
3. 2 RAG questions — one per PDF, each asking about a different policy topic than
   refund timelines / failed delivery attempts.
4. Choose a unique user_query that combines the SQL and RAG angles.
5. focus_areas must match the chosen queries (3 items).
6. Use a random 4-digit suffix for request_id, e.g. "REQ-SALES-SYNTH-4821".
7. Do NOT include "embedding" fields — they are added by the server.
8. Return ONLY a valid JSON object — no markdown, no code fences.

OUTPUT SCHEMA (fill in all <NEW> placeholders):
{
  "request_id": "REQ-SALES-SYNTH-<4-digit>",
  "app_context": {
    "application_name": "Universal Synthesizer Agent App",
    "agent_name": "Domain Synthesizer Agent",
    "model": "gemma-4-26b-a4b-it",
    "domain": "Sales",
    "objective": "<NEW: 1 sentence describing this scenario's goal>"
  },
  "persona": {
    "role": "Sales Synthesizer Agent",
    "instruction": "You are a sales domain synthesizer agent. Your purpose is to synthesize structured order data (cancellations, shipments, returns) with sales policy guidance from the knowledge base. Always treat order status and transaction records as factual. Use knowledge base chunks for policy rules, refund timelines, and eligibility criteria. Present findings in a clear, customer-operations-friendly tone."
  },
  "user_query": "<NEW: aggregate analysis question covering both SQL findings and policy>",
  "input_contract": {
    "structured_input_type": "SQL",
    "unstructured_input_type": "Embedding similarity search",
    "structured_tables_allowed": [
      "semantic_layer.sales_cancellation",
      "semantic_layer.sales_shipment"
    ],
    "rag_table": "tracopp.rag_document_chunks",
    "allowed_rag_documents_only": [
      "Sales_Cancellation_KnowledgeBase.pdf",
      "Sales_Shipment_KnowledgeBase.pdf"
    ]
  },
  "structured_inputs": {
    "sql_scripts": [
      {"query_id": "SQL_001", "label": "<label>", "source_table": "semantic_layer.sales_cancellation", "sql": "<SELECT aggregate query>"},
      {"query_id": "SQL_002", "label": "<label>", "source_table": "semantic_layer.sales_cancellation", "sql": "<SELECT aggregate query>"},
      {"query_id": "SQL_003", "label": "<label>", "source_table": "semantic_layer.sales_shipment",    "sql": "<SELECT aggregate query>"},
      {"query_id": "SQL_004", "label": "<label>", "source_table": "semantic_layer.sales_shipment",    "sql": "<SELECT aggregate query>"}
    ]
  },
  "unstructured_inputs": {
    "similarity_search_inputs": [
      {
        "embedding_id": "EMB_001",
        "label": "<label for cancellation question>",
        "content": "<NEW question about a cancellation policy topic>",
        "top_k": 3,
        "rag_table": "tracopp.rag_document_chunks",
        "document_filter": "Sales_Cancellation_KnowledgeBase.pdf"
      },
      {
        "embedding_id": "EMB_002",
        "label": "<label for shipment question>",
        "content": "<NEW question about a shipment policy topic>",
        "top_k": 3,
        "rag_table": "tracopp.rag_document_chunks",
        "document_filter": "Sales_Shipment_KnowledgeBase.pdf"
      }
    ]
  },
  "execution_flow": {
    "steps": ["validate_json", "execute_sql", "retrieve_rag", "synthesize", "render_output"],
    "parallel_sql_execution": true,
    "parallel_rag_execution": true,
    "stop_on_critical_error": false,
    "timeout_seconds": 120
  },
  "synthesis_instruction": {
    "treat_structured_as": "source_of_truth",
    "treat_unstructured_as": "policy_and_guidance",
    "conflict_resolution": "structured_data_wins",
    "response_language": "English",
    "response_tone": "professional",
    "include_recommendations": true,
    "include_confidence_score": false,
    "max_response_length": "detailed",
    "focus_areas": ["<area1>", "<area2>", "<area3>"]
  },
  "expected_output_schema": {
    "sections": [
      {"section_id": "structured_summary", "title": "Structured Data Summary", "display_type": "table_and_chart", "chart_type": "bar", "source": "sql"},
      {"section_id": "policy_guidance",    "title": "Policy & Guidance",        "display_type": "text",           "source": "llm"},
      {"section_id": "synthesized_answer", "title": "Synthesized Answer",       "display_type": "text",           "source": "llm"},
      {"section_id": "recommendations",    "title": "Recommendations",          "display_type": "list",           "source": "llm"}
    ]
  },
  "error_handling": {
    "on_sql_error": "continue_with_warning",
    "on_rag_error": "continue_with_warning",
    "on_llm_error": "return_partial_results",
    "max_retries": 2,
    "fallback_message": "Unable to synthesize a complete response. Partial results are shown below."
  }
}"""


# ── Route ───────────────────────────────────────────────────────────────────────

@router.post("/generate-sample-json")
async def generate_sample_json():
    s = get_settings()
    if not s.gemini_api_key:
        return JSONResponse({"error": "GEMINI_API_KEY not configured"}, status_code=500)

    loop = asyncio.get_event_loop()

    # ── Step 1: LLM generates JSON skeleton (no embeddings) ───────────────────
    def _call_llm() -> dict:
        client = genai.Client(api_key=s.gemini_api_key)
        response = client.models.generate_content(
            model=s.gemini_model,
            contents=_GENERATION_PROMPT,
            config=types.GenerateContentConfig(
                temperature=0.85,
                max_output_tokens=2048,
            ),
        )
        raw = response.text if hasattr(response, "text") else str(response)
        cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
        return json.loads(cleaned)

    try:
        payload = await loop.run_in_executor(None, _call_llm)
    except json.JSONDecodeError as e:
        return JSONResponse({"error": f"LLM returned invalid JSON: {e}"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": f"LLM generation failed: {e}"}, status_code=500)

    # ── Step 2: Generate real 1024-dim embeddings for each RAG question ───────
    def _add_embeddings(data: dict) -> dict:
        inputs = data.get("unstructured_inputs", {}).get("similarity_search_inputs", [])
        for item in inputs:
            content = item.get("content", "")
            if content:
                try:
                    item["embedding"] = generate_embedding(content, s.gemini_api_key)
                except Exception:
                    # Graceful fallback: zero vector keeps the schema valid
                    item["embedding"] = [0.0] * 1024
        return data

    try:
        payload = await loop.run_in_executor(None, _add_embeddings, payload)
    except Exception as e:
        return JSONResponse({"error": f"Embedding generation failed: {e}"}, status_code=500)

    return JSONResponse(payload)
