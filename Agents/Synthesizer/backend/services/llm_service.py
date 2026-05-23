"""
LLM synthesis service.
Uses Groq (llama-3.3-70b-versatile) — same provider as ARIA / SAGE / VALKYRIE.
"""
import json
import re
from groq import Groq

from config import get_settings


# ── Prompt helpers ─────────────────────────────────────────────────────────────

def _format_sql_results(sql_results: list) -> str:
    parts = []
    for r in sql_results:
        parts.append(f"▶ Query: {r['query_id']} — {r.get('label', '')}")
        parts.append(f"  Table : {r['source_table']}")
        parts.append(f"  Status: {r['status']}")
        if r["status"] == "success":
            parts.append(f"  Rows  : {r['row_count']}")
            if r["rows"]:
                headers = r.get("columns", list(r["rows"][0].keys()))
                parts.append("  " + " | ".join(headers))
                parts.append("  " + "-" * 60)
                for row in r["rows"][:15]:
                    parts.append("  " + " | ".join(str(v) for v in row.values()))
        else:
            parts.append(f"  Error : {r.get('error', 'unknown')}")
        parts.append("")
    return "\n".join(parts) or "No SQL results available."


def _format_rag_results(rag_results: list) -> str:
    if not rag_results:
        return "No RAG inputs provided."
    parts = []
    for r in rag_results:
        label   = r.get("label", r.get("embedding_id", ""))
        content = r.get("content", "")
        parts.append(f"▶ QUESTION [{label}]: {content}")
        if r["status"] == "success":
            for i, chunk in enumerate(r.get("chunks", [])[:3], 1):
                score = chunk.get("similarity_score")
                score_str = f"{float(score):.4f}" if score is not None else "n/a"
                text = str(chunk.get("chunk_text", ""))[:800]
                parts.append(f"\n  [Chunk {i} | sim={score_str}]")
                parts.append(f"  {text}")
        else:
            parts.append(f"  Error: {r.get('error', 'unknown')}")
        parts.append("")
    return "\n".join(parts)


def _build_output_format(sections: list) -> str:
    llm_sections = [s for s in sections if s.get("source") == "llm"]
    if not llm_sections:
        llm_sections = [
            {"section_id": "synthesized_answer", "title": "Synthesized Answer", "display_type": "text"},
            {"section_id": "recommendations",    "title": "Recommendations",    "display_type": "list"},
        ]

    lines = ["Return a valid JSON object with exactly these keys:"]
    for s in llm_sections:
        sid     = s["section_id"]
        display = s.get("display_type", "text")
        title   = s.get("title", sid)
        if display == "list":
            lines.append(f'  "{sid}": ["item 1", "item 2", ...]   // {title}')
        else:
            lines.append(f'  "{sid}": "..."   // {title}')
    lines.append("")
    lines.append("Output ONLY the raw JSON object — no markdown fences, no extra text.")
    lines.append("For all text fields use \\n for newlines. Use ## and ### for headings, **text** for bold.")
    return "\n".join(lines)


def _build_prompt(payload: dict, sql_results: list, rag_results: list) -> str:
    persona      = payload.get("persona", {})
    app_ctx      = payload.get("app_context", {})
    user_query   = payload.get("user_query", "")
    synthesis    = payload.get("synthesis_instruction", {})
    output_schema = payload.get("expected_output_schema", {})
    sections     = output_schema.get("sections", [])

    role        = persona.get("role", "Domain Synthesizer Agent")
    instruction = persona.get("instruction", "You are a professional domain synthesizer agent.")
    domain      = app_ctx.get("domain", "Unknown")

    treat_structured   = synthesis.get("treat_structured_as",  "source of truth for transactional data")
    treat_unstructured = synthesis.get("treat_unstructured_as", "policy and guidance source")
    conflict_rule      = synthesis.get("conflict_resolution",  "structured data takes precedence")
    tone               = synthesis.get("response_tone",        "professional")
    language           = synthesis.get("response_language",    "English")
    include_recs       = synthesis.get("include_recommendations", True)
    focus              = synthesis.get("focus_areas", [])

    output_format = _build_output_format(sections)

    return f"""You are a {role} operating in the {domain} domain.

PERSONA INSTRUCTION:
{instruction}

USER QUERY:
{user_query}

SYNTHESIS RULES:
- Treat structured SQL data as: {treat_structured}
- Treat unstructured RAG data as: {treat_unstructured}
- Conflict resolution: {conflict_rule}
- Response tone: {tone}
- Language: {language}
- Include recommendations: {include_recs}
{("- Focus areas: " + ", ".join(focus)) if focus else ""}

─── STRUCTURED DATA (SQL RESULTS) ───────────────────────────────────────────
{_format_sql_results(sql_results)}

─── UNSTRUCTURED DATA (RAG / KNOWLEDGE BASE CHUNKS) ─────────────────────────
{_format_rag_results(rag_results)}

─── OUTPUT FORMAT ────────────────────────────────────────────────────────────
{output_format}
"""


def _extract_json(raw: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"synthesized_answer": cleaned}


def synthesize_with_llm(payload: dict, sql_results: list, rag_results: list) -> dict:
    """Call Groq and return parsed synthesis sections."""
    s = get_settings()

    if not s.groq_api_key:
        return {"synthesized_answer": "LLM not configured — GROQ_API_KEY is missing."}

    client = Groq(api_key=s.groq_api_key)
    prompt = _build_prompt(payload, sql_results, rag_results)

    response = client.chat.completions.create(
        model=s.groq_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=4096,
    )

    raw_text = response.choices[0].message.content
    return _extract_json(raw_text)


def test_llm() -> dict:
    """Health-check: verify Groq API key and model are reachable."""
    s = get_settings()
    if not s.groq_api_key:
        return {"status": "error", "error": "GROQ_API_KEY not configured"}
    try:
        client = Groq(api_key=s.groq_api_key)
        response = client.chat.completions.create(
            model=s.groq_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        return {"status": "ok", "model": s.groq_model}
    except Exception as e:
        return {"status": "error", "error": str(e)}
