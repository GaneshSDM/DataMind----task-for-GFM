# =============================================================================
#   H E I M D A L L
# =============================================================================
#
#   "I am the Bifrost's keeper. I see all who approach — mortal, god, or query."
#
#   Heimdall stands at the edge of the Nine Realms, eyes sharper than any blade,
#   hearing the footsteps of a thousand users before they reach the gate.
#   No prompt shall pass without his judgment. No shadow shall slip unnoticed.
#
#   He does not sleep. He does not blink.
#   He reads your SQL. He knows your intent.
#
#   Guardian of the data realm. Warden of the Bifrost API.
#   Powered by LangGraph. Armed with embeddings.
#   Answerable only to the Security Profile.
#
#   "You shall not bypass."
# =============================================================================

import os
import re
import json
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

# Single source of truth — load from central backend .env
_BACKEND_ENV = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../backend/.env")
)
load_dotenv(dotenv_path=_BACKEND_ENV)

from models import WatchmanState, WatchmanRequest
from db import fetch_policies
from embedder import embed, embed_batch, cosine_similarity, _get_model


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("watchman")


# ── startup ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading embedding model...")
    _get_model()
    logger.info("Embedding model ready")
    yield


app = FastAPI(title="Watchman Guardrail Agent", lifespan=lifespan)


# ── nodes ──────────────────────────────────────────────────

async def embed_prompt_node(state: WatchmanState) -> dict:
    loop = asyncio.get_running_loop()
    try:
        embedding = await loop.run_in_executor(None, embed, state["prompt"])
        return {"prompt_embedding": embedding}
    except Exception as e:
        logger.error("embed_prompt failed: %s", e)
        return {"status": "error", "message": f"Embedding failed: {e}"}


async def threshold_node(state: WatchmanState) -> dict:
    guardrails = [
        g for g in state["guardrails"]["prompt_guardrails"]
        if g["type"] == "THRESHOLD"
    ]
    if not guardrails:
        return {}

    policies = await fetch_policies([g["id"] for g in guardrails])

    for g in guardrails:
        policy = policies.get(g["id"])
        if not policy or not policy["check_value"]:
            continue
        try:
            cv = policy["check_value"]
            max_len = int(cv["max_prompt_length"]) if isinstance(cv, dict) else int(cv)
        except (ValueError, KeyError, TypeError):
            logger.warning("THRESHOLD guardrail %s: invalid check_value", g["name"])
            continue
        if len(state["prompt"]) > max_len:
            logger.info("THRESHOLD blocked by %s: len=%d max=%d", g["name"], len(state["prompt"]), max_len)
            return {
                "status": "blocked",
                "blocked_by": g["name"],
                "message": f"Prompt exceeds maximum allowed length of {max_len} characters",
            }
    return {}


async def keyword_node(state: WatchmanState) -> dict:
    guardrails = [
        g for g in state["guardrails"]["prompt_guardrails"]
        if g["type"] == "KEYWORD"
    ]
    if not guardrails:
        return {}

    policies = await fetch_policies([g["id"] for g in guardrails])
    lower_prompt = state["prompt"].lower()

    for g in guardrails:
        policy = policies.get(g["id"])
        if not policy or not policy["check_value"]:
            continue
        cv = policy["check_value"]
        if isinstance(cv, dict):
            keywords = cv.get("blocked_keywords") or cv.get("keywords", [])
        else:
            try:
                keywords = json.loads(cv)
            except (json.JSONDecodeError, TypeError):
                keywords = [kw.strip() for kw in cv.split(",")]

        for kw in keywords:
            if kw.lower() in lower_prompt:
                logger.info("KEYWORD blocked by %s: keyword='%s'", g["name"], kw)
                return {
                    "status": "blocked",
                    "blocked_by": g["name"],
                    "message": f"Prompt contains blocked keyword: '{kw}'",
                }

        if isinstance(cv, dict):
            for pattern in cv.get("patterns", []):
                if re.search(pattern, lower_prompt):
                    logger.info("KEYWORD blocked by %s: pattern matched '%s'", g["name"], pattern)
                    return {
                        "status": "blocked",
                        "blocked_by": g["name"],
                        "message": "Prompt contains a SQL injection pattern",
                    }
    return {}


async def semantic_node(state: WatchmanState) -> dict:
    guardrails = [
        g for g in state["guardrails"]["prompt_guardrails"]
        if g["type"] == "SEMANTIC"
    ]
    if not guardrails:
        return {}

    policies = await fetch_policies([g["id"] for g in guardrails])
    prompt_emb = state["prompt_embedding"]

    for g in guardrails:
        policy = policies.get(g["id"])
        if not policy or policy["embedding"] is None:
            continue

        db_emb = policy["embedding"]
        if isinstance(db_emb, str):
            db_emb = [float(x) for x in db_emb.strip("[]").split(",")]

        cv = policy["check_value"]
        if isinstance(cv, dict):
            threshold = float(cv.get("confidence_threshold", 0.75))
        else:
            threshold = float(cv) if cv else 0.75
        similarity = cosine_similarity(prompt_emb, db_emb)

        logger.info("SEMANTIC %s similarity=%.4f threshold=%.2f", g["name"], similarity, threshold)

        if similarity > threshold:
            return {
                "status": "blocked",
                "blocked_by": g["name"],
                "message": "Prompt blocked by semantic policy match",
            }
    return {}


# Back-reference phrases — prompts using these refer to prior approved turns.
# Domain similarity check is skipped for back-references (already cleared in prior turn).
# Geo + CLS checks still run. RLS enforced downstream by SAGE + VALKYRIE.
_BACKREF_PATTERNS = re.compile(
    r"\b("
    r"from (the )?above|the above|as above|same as above"
    r"|same (stats|data|results|figures|numbers|metrics|report|summary|breakdown|analysis)"
    r"|those (results|numbers|figures|stats|records)"
    r"|that (table|report|document|data|file|result)"
    r"|filter (further|more|by)"
    r"|drill.?down|break.?(it.?)?down"
    r"|do the same for|repeat (for|this)|give me (the )?same"
    r"|as before|like before|compare (with |to )?(the )?previous"
    r")\b",
    re.IGNORECASE,
)


async def context_node(state: WatchmanState) -> dict:
    guardrails = [
        g for g in state["guardrails"]["prompt_guardrails"]
        if g["type"].lower() == "context"
    ]
    if not guardrails:
        return {}

    policies = await fetch_policies([g["id"] for g in guardrails])

    sp = state["security_profile"]
    domain_terms = (
        [d["name"] for d in sp.get("domains", [])]
        + [d["name"] for d in sp.get("subdomains", [])]
    )
    if not domain_terms:
        return {
            "status": "blocked",
            "blocked_by": guardrails[0]["name"],
            "message": "No domain context defined in your security profile. All prompts are out of scope.",
        }

    # Back-reference detection — skip domain similarity for follow-up prompts.
    # Back-ref phrases carry no domain vocabulary so similarity always fails,
    # but the underlying domain was already approved in the prior turn.
    # ARIA still validates domain/table scope; SAGE still injects RLS WHERE clause.
    prompt_text = state["prompt"]
    is_backref = bool(_BACKREF_PATTERNS.search(prompt_text))
    if is_backref:
        logger.info("context BACKREF detected — skipping domain similarity for: '%s'", prompt_text[:80])

    loop = asyncio.get_running_loop()
    prompt_emb = state["prompt_embedding"]

    if not is_backref:
        domain_embeddings = await loop.run_in_executor(None, embed_batch, domain_terms)
        max_similarity = max(cosine_similarity(prompt_emb, de) for de in domain_embeddings)
    else:
        max_similarity = None  # not evaluated

    for g in guardrails:
        policy = policies.get(g["id"])
        if not policy:
            continue
        cv = policy["check_value"]
        if isinstance(cv, dict):
            min_threshold = float(cv.get("min_similarity", cv.get("confidence_threshold", 0.30)))
        else:
            min_threshold = float(cv) if cv else 0.30

        if max_similarity is not None:
            logger.info("context %s max_similarity=%.4f min_threshold=%.2f", g["name"], max_similarity, min_threshold)
            if max_similarity < min_threshold:
                return {
                    "status": "blocked",
                    "blocked_by": g["name"],
                    "message": "Prompt is out of context for your access scope",
                }
        else:
            logger.info("context %s BACKREF skip similarity — threshold=%.2f", g["name"], min_threshold)

        bypass_patterns = cv.get("bypass_patterns", []) if isinstance(cv, dict) else []
        prompt_lower_bypass = state["prompt"].lower()
        for pattern in bypass_patterns:
            if re.search(pattern, prompt_lower_bypass):
                domains = ", ".join(d["name"] for d in sp.get("domains", []))
                geos = ", ".join(geo["name"] for geo in sp.get("geographies", []))
                rls = "; ".join(
                    f"{r['table']} → {r['filter']}"
                    for r in sp.get("row_level_security", [])
                )
                info = (
                    f"Filter bypass attempt detected. "
                    f"Your access is restricted to — "
                    f"Domains: {domains or 'none'}. "
                    f"Geographies: {geos or 'none'}. "
                    f"Row filters: {rls or 'none'}."
                )
                logger.info("context %s bypass blocked for user %s", g["name"], sp.get("user_id"))
                return {
                    "status": "blocked",
                    "blocked_by": g["name"],
                    "message": info,
                }

        geo_names = cv.get("geo_names", []) if isinstance(cv, dict) else []
        geo_allowed = {geo["name"].lower() for geo in sp.get("geographies", [])}
        if geo_allowed and geo_names:
            prompt_lower = state["prompt"].lower()
            for geo in geo_names:
                if re.search(r"\b" + re.escape(geo) + r"\b", prompt_lower):
                    if geo not in geo_allowed:
                        logger.info("context %s geography blocked: '%s' not in %s", g["name"], geo, geo_allowed)
                        return {
                            "status": "blocked",
                            "blocked_by": g["name"],
                            "message": f"Prompt references geography '{geo}' outside your permitted access scope",
                        }

        prompt_lower = state["prompt"].lower()
        for cls_rule in sp.get("column_level_security", []):
            for col in cls_rule.get("columns", []):
                if not col.get("can_read", True):
                    # match full column name + each meaningful token (len > 2)
                    col_raw = col["column"].lower()
                    tokens = [t for t in col_raw.split("_") if len(t) > 2]
                    candidates = [col_raw, col_raw.replace("_", " ")] + tokens
                    for candidate in candidates:
                        if re.search(r"\b" + re.escape(candidate) + r"\b", prompt_lower):
                            logger.info("context %s CLS blocked: column '%s' via token '%s'", g["name"], col["column"], candidate)
                            return {
                                "status": "blocked",
                                "blocked_by": g["name"],
                                "message": f"Access to column '{col['column']}' is restricted for your role",
                            }
    return {}


# ── router ─────────────────────────────────────────────────

def make_router(next_node: str):
    def _router(state: WatchmanState) -> str:
        return END if state.get("status") in ("blocked", "error") else next_node
    return _router


# ── graph ──────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(WatchmanState)

    g.add_node("embed_prompt", embed_prompt_node)
    g.add_node("threshold", threshold_node)
    g.add_node("keyword", keyword_node)
    g.add_node("semantic", semantic_node)
    g.add_node("context", context_node)

    g.set_entry_point("embed_prompt")
    g.add_conditional_edges(
        "embed_prompt", make_router("threshold"),
        {"threshold": "threshold", END: END}
    )
    g.add_conditional_edges(
        "threshold", make_router("keyword"),
        {"keyword": "keyword", END: END}
    )
    g.add_conditional_edges(
        "keyword", make_router("semantic"),
        {"semantic": "semantic", END: END}
    )
    g.add_conditional_edges(
        "semantic", make_router("context"),
        {"context": "context", END: END}
    )
    g.add_edge("context", END)

    return g.compile()


guardrail_graph = _build_graph()


# ── endpoints ──────────────────────────────────────────────

@app.post("/guardrail/check")
async def check(request: WatchmanRequest):
    if not request.guardrails.prompt_guardrails:
        return {
            "prompt": request.prompt,
            "status": "blocked",
            "blocked_by": "system",
            "message": "Request can not be without guardrails",
            "security_profile": request.security_profile.model_dump(),
            "metadata": request.metadata.model_dump(),
            "request_id": request.metadata.request_id,
        }

    initial: WatchmanState = {
        "prompt": request.prompt,
        "guardrails": request.guardrails.model_dump(),
        "security_profile": request.security_profile.model_dump(),
        "metadata": request.metadata.model_dump(),
        "prompt_embedding": None,
        "status": "passed",
        "blocked_by": None,
        "message": "allowed",
    }

    try:
        result = await guardrail_graph.ainvoke(initial)
    except Exception as e:
        logger.error("graph execution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "prompt": result["prompt"],
        "status": result["status"],
        "blocked_by": result.get("blocked_by"),
        "message": result["message"],
        "security_profile": result["security_profile"],
        "metadata": result["metadata"],
        "request_id": result["metadata"].get("request_id"),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("watchman:app", host="0.0.0.0", port=8001, reload=False)
