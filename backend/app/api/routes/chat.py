import json
import uuid
import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks

logger = logging.getLogger(__name__)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import (
    ChatHistory, ChatMessage,
    UserSecurityGroup, SecurityGroup, SecurityGroupRLS, SecurityGroupCLS,
    SecurityGroupDomain, SecurityGroupSubDomain, SecurityGroupGeography,
    RowLevelSecurity, ColumnLevelSecurity, ColumnSecurityMapping,
    Domain, SubDomain, Geography,
    UserRole, Role
)
from app.schemas.schemas import SendPromptRequest

router = APIRouter()

# User profile cache (per-user with TTL)
_user_profile_cache = {}
PROFILE_CACHE_TTL = 300  # 5 minutes


def invalidate_user_profile_cache(user_id):
    _user_profile_cache.pop(user_id, None)


def get_cached_user_profile(db, user_id):
    now = time.time()
    if user_id in _user_profile_cache:
        profile, cached_time = _user_profile_cache[user_id]
        if now - cached_time < PROFILE_CACHE_TTL:
            return profile

    profile = build_security_payload(db, user_id)
    _user_profile_cache[user_id] = (profile, now)
    return profile


def get_user_role_name(db, user_id):
    ur = db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.is_active == True).first()
    if ur:
        role = db.query(Role).filter(Role.role_id == ur.role_id).first()
        return role.role_name if role else "User"
    return "User"


def get_user_security_group_ids(db, user_id):
    """Return all active security group IDs for user."""
    usgs = db.query(UserSecurityGroup).filter(
        UserSecurityGroup.user_id == user_id,
        UserSecurityGroup.is_active == True
    ).all()
    return [u.security_group_id for u in usgs]


def build_security_payload(db, user_id, security_group_id=None, security_group_ids=None):
    role = get_user_role_name(db, user_id)

    # Use provided SG list, single SG, or all assigned SGs
    if security_group_ids:
        sg_ids = security_group_ids
    elif security_group_id:
        sg_ids = [security_group_id]
    else:
        sg_ids = get_user_security_group_ids(db, user_id)

    sg_names, domain_list, subdomain_list, geo_list, rls_list, cls_list = [], [], [], [], [], []
    seen_rls, seen_cls, seen_domain, seen_subdomain, seen_geo = set(), set(), set(), set(), set()

    for sgid in sg_ids:
        sg = db.query(SecurityGroup).filter(
            SecurityGroup.security_group_id == sgid,
            SecurityGroup.is_active == True
        ).first()
        if not sg:
            continue
        sg_names.append(sg.security_group_name)

        # Domains
        for r in db.query(SecurityGroupDomain).filter(
            SecurityGroupDomain.security_group_id == sgid,
            SecurityGroupDomain.is_active == True
        ).all():
            if r.domain_id not in seen_domain:
                d = db.query(Domain).filter(Domain.domain_id == r.domain_id, Domain.is_active == True).first()
                if d:
                    domain_list.append({"id": d.domain_id, "name": d.domain_name})
                    seen_domain.add(r.domain_id)

        # SubDomains
        for r in db.query(SecurityGroupSubDomain).filter(
            SecurityGroupSubDomain.security_group_id == sgid,
            SecurityGroupSubDomain.is_active == True
        ).all():
            if r.sub_domain_id not in seen_subdomain:
                sd = db.query(SubDomain).filter(SubDomain.sub_domain_id == r.sub_domain_id, SubDomain.is_active == True).first()
                if sd:
                    subdomain_list.append({"id": sd.sub_domain_id, "name": sd.sub_domain_name})
                    seen_subdomain.add(r.sub_domain_id)

        # Geographies
        for r in db.query(SecurityGroupGeography).filter(
            SecurityGroupGeography.security_group_id == sgid,
            SecurityGroupGeography.is_active == True
        ).all():
            if r.geo_id not in seen_geo:
                g = db.query(Geography).filter(Geography.geo_id == r.geo_id, Geography.is_active == True).first()
                if g:
                    geo_list.append({"id": g.geo_id, "name": g.geo_name})
                    seen_geo.add(r.geo_id)

        # RLS
        for r in db.query(SecurityGroupRLS).filter(
            SecurityGroupRLS.security_group_id == sgid,
            SecurityGroupRLS.is_active == True
        ).all():
            if r.rls_id not in seen_rls:
                rls = db.query(RowLevelSecurity).filter(
                    RowLevelSecurity.rls_id == r.rls_id,
                    RowLevelSecurity.is_active == True
                ).first()
                if rls:
                    rls_list.append({"name": rls.rls_name, "table": rls.target_table, "filter": rls.filter_expression})
                    seen_rls.add(r.rls_id)

        # CLS with column details
        for c in db.query(SecurityGroupCLS).filter(
            SecurityGroupCLS.security_group_id == sgid,
            SecurityGroupCLS.is_active == True
        ).all():
            if c.cls_id not in seen_cls:
                cls = db.query(ColumnLevelSecurity).filter(
                    ColumnLevelSecurity.cls_id == c.cls_id,
                    ColumnLevelSecurity.is_active == True
                ).first()
                if cls:
                    cols = db.query(ColumnSecurityMapping).filter(
                        ColumnSecurityMapping.cls_id == cls.cls_id,
                        ColumnSecurityMapping.is_active == True
                    ).all()
                    cls_list.append({
                        "name": cls.cls_name,
                        "table": cls.target_table,
                        "columns": [
                            {"column": cm.column_name, "can_read": cm.can_read, "can_write": cm.can_write}
                            for cm in cols
                        ]
                    })
                    seen_cls.add(c.cls_id)

    return {
        "user_id": f"USR{user_id:03d}",
        "role": role,
        "security_groups": sg_names,
        "domains": domain_list,
        "subdomains": subdomain_list,
        "geographies": geo_list,
        "row_level_security": rls_list,
        "column_level_security": cls_list,
    }


# ── Conversation context (persistent via assistant message payload) ────────────
_MAX_CONTEXT_TURNS = 3


def _context_block_with_summary(snapshot: list, summary: str) -> str:
    """Build full context string for ARIA: summary + recent turns."""
    parts = []
    if summary and summary.strip():
        parts.append(f"[SUMMARY] {summary.strip()}")
    if snapshot:
        lines = []
        for e in snapshot[-_MAX_CONTEXT_TURNS:]:
            # Skip failed pipeline turns — only inject context from successful runs
            if not e.get("pipeline_success", True):
                continue
            domain               = e.get("domain", "")
            table                = e.get("table", "")
            cols                 = ", ".join(e.get("columns", [])[:5])
            description          = e.get("description", "")
            user_prompt          = e.get("user_prompt", "")
            unstructured_source  = e.get("unstructured_source", "")
            # Infer data_source: use saved value if present; else infer from table presence
            if "data_source" in e:
                data_source = e["data_source"]
            elif table:
                data_source = "Structured"
            elif unstructured_source:
                data_source = "Unstructured"
            else:
                data_source = "Unknown"
            line = f"  [{domain}] data_source:{data_source}"
            if table:
                line += f" | table:{table}"
            if unstructured_source:
                line += f" | source:{unstructured_source}"
            if cols:
                line += f" | cols:{cols}"
            if description:
                line += f" | computed:{description[:80]}"
            if user_prompt:
                line += f" | Q:\"{user_prompt[:80]}\""
            lines.append(line)
        if lines:
            parts.append(f"[RECENT TURNS]\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _load_context_data(db, chat_id: int) -> tuple[list, str]:
    """Load context_snapshot and chat_summary from the most recent assistant message."""
    if not chat_id:
        return [], ""
    last_asst = (
        db.query(ChatMessage)
        .filter(ChatMessage.chat_id == chat_id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_date.desc())
        .first()
    )
    if not last_asst or not isinstance(last_asst.payload, dict):
        return [], ""
    snapshot = last_asst.payload.get("context_snapshot", [])
    summary  = last_asst.payload.get("chat_summary", "")
    return snapshot, summary


def _build_context_snapshot(
    prior_snapshot: list, intent_result: dict, user_prompt: str, pipeline_success: bool = False
) -> list:
    """Append current turn to snapshot and trim to _MAX_CONTEXT_TURNS.
    Stores user_prompt (already Heimdall-checked) + ARIA intent metadata.
    pipeline_success=True only when SPYDER synthesis succeeded.
    Failed turns stored but excluded from ARIA context (prevents bad-turn context pollution).
    No synthesis output stored — prevents guardrail bypass on follow-up turns.
    """
    intents = (intent_result or {}).get("intents", [])
    if not intents:
        return list(prior_snapshot or [])
    first = intents[0]
    entry = {
        "domain":               first.get("domain", ""),
        "table":                first.get("structured_table", ""),
        "columns":              first.get("relevant_columns", [])[:5],
        "description":          first.get("description", "")[:120],
        "user_prompt":          user_prompt[:100],
        "pipeline_success":     pipeline_success,
        "data_source":          first.get("data_source", "Structured"),
        "unstructured_source":  (first.get("unstructured_source") or "")[:120],
    }
    updated = list(prior_snapshot or [])
    updated.append(entry)
    return updated[-_MAX_CONTEXT_TURNS:]


async def _generate_summary(existing_summary: str, turns: list) -> str:
    """Call LLM to produce updated rolling summary. Metadata only — no data values."""
    import os
    from openai import AsyncOpenAI

    api_key  = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    model    = os.getenv("LLM_MODEL") or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        logger.warning("SUMMARY_SKIP no LLM_API_KEY set")
        return existing_summary

    turns_text = "\n".join(
        f"  [{e.get('domain','')}] {e.get('table','')} | {e.get('description','')} | Q: {e.get('user_prompt','')}"
        for e in turns
    )
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=150,
            messages=[
                {"role": "system", "content": (
                    "Summarise a data analyst's conversation context in 1-2 sentences. "
                    "Cover: domains accessed, tables queried, analysis focus. "
                    "Never include data values, result numbers, or sensitive content. "
                    "Plain text only, no markdown."
                )},
                {"role": "user", "content": (
                    f"Existing summary: {existing_summary or 'None yet'}\n\n"
                    f"Turns to incorporate:\n{turns_text}\n\n"
                    f"Output updated summary:"
                )},
            ],
        )
        latency_ms = int((time.time() - t0) * 1000)
        tokens_in  = resp.usage.prompt_tokens if resp.usage else 0
        tokens_out = resp.usage.completion_tokens if resp.usage else 0
        logger.info(
            "SUMMARY_GEN_OK latency_ms=%d tokens_in=%d tokens_out=%d model=%s",
            latency_ms, tokens_in, tokens_out, model,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        logger.warning("SUMMARY_GEN_FAIL latency_ms=%d error=%s", latency_ms, e)
        return existing_summary


async def _background_summary_update(
    chat_id: int, message_id: int, prior_snapshot: list, existing_summary: str
) -> None:
    """Background task: generate rolling summary and persist it on the just-saved assistant message."""
    from app.db.session import SessionLocal
    t0 = time.time()
    logger.info(
        "SUMMARY_START chat_id=%d msg_id=%d turns_to_summarise=%d had_existing=%s",
        chat_id, message_id, len(prior_snapshot), bool(existing_summary),
    )
    db = SessionLocal()
    try:
        new_summary = await _generate_summary(existing_summary, prior_snapshot)
        if not new_summary:
            logger.warning("SUMMARY_EMPTY chat_id=%d msg_id=%d — skipping DB write", chat_id, message_id)
            return
        msg = db.query(ChatMessage).filter(ChatMessage.message_id == message_id).first()
        if msg and isinstance(msg.payload, dict):
            updated = dict(msg.payload)
            updated["chat_summary"] = new_summary
            msg.payload = updated
            db.commit()
            logger.info(
                "SUMMARY_SAVED chat_id=%d msg_id=%d total_ms=%d summary_len=%d",
                chat_id, message_id, int((time.time() - t0) * 1000), len(new_summary),
            )
        else:
            logger.warning("SUMMARY_MSG_NOT_FOUND chat_id=%d msg_id=%d", chat_id, message_id)
    except Exception as exc:
        logger.warning(
            "SUMMARY_ERROR chat_id=%d msg_id=%d total_ms=%d error=%s",
            chat_id, message_id, int((time.time() - t0) * 1000), exc,
        )
    finally:
        db.close()


async def run_guardrail_pipeline(prompt, guardrails_list, security_profile, metadata):
    """
    Calls the LangGraph orchestrator → Heimdall guardrail microservice.
    Returns OrchestratorState dict.
    """
    from app.agents.orchestrator import run_pipeline

    prompt_guardrails = [
        {"id": str(g.id), "name": g.policy_name, "type": g.check_type}
        for g in guardrails_list
    ]
    guardrails_payload = {"prompt_guardrails": prompt_guardrails, "response_guardrails": []}

    return await run_pipeline(
        prompt=prompt,
        guardrails=guardrails_payload,
        security_profile=security_profile,
        metadata=metadata,
    )


@router.get("/")
def list_chats(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    chats = db.query(ChatHistory).filter(
        ChatHistory.user_id == current_user.user_id,
        ChatHistory.is_active == True
    ).order_by(ChatHistory.updated_date.desc().nullslast(), ChatHistory.created_date.desc()).all()
    return [{"ChatID": c.chat_id, "Title": c.title, "CreatedDate": c.created_date, "UpdatedDate": c.updated_date} for c in chats]


@router.get("/{chat_id}/messages")
def get_messages(chat_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(ChatHistory).filter(
        ChatHistory.chat_id == chat_id,
        ChatHistory.user_id == current_user.user_id
    ).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    msgs = db.query(ChatMessage).filter(ChatMessage.chat_id == chat_id).order_by(ChatMessage.created_date).all()
    result = []
    for m in msgs:
        row = {"MessageID": m.message_id, "Role": m.role, "Content": m.content, "Payload": m.payload, "CreatedDate": m.created_date}
        if m.role == "assistant" and m.payload and isinstance(m.payload, dict):
            row["SpyderResult"] = m.payload.get("spyder_result")
        result.append(row)
    return result


@router.post("/send")
async def send_prompt(request: Request, payload: SendPromptRequest, background_tasks: BackgroundTasks, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    request_id = str(uuid.uuid4())

    # Build security profile — use provided SG list, single SG, or all assigned
    sg_ids = payload.security_group_ids or None
    sg_id = payload.security_group_id or None
    if sg_ids:
        security_profile = build_security_payload(db, current_user.user_id, security_group_ids=sg_ids)
    elif sg_id:
        security_profile = build_security_payload(db, current_user.user_id, security_group_id=sg_id)
    else:
        security_profile = get_cached_user_profile(db, current_user.user_id)

    # Load persistent context snapshot + rolling summary from last assistant message
    prior_snapshot, existing_summary = _load_context_data(db, payload.chat_id)
    logger.info(
        "CONTEXT_LOAD chat_id=%s snapshot_turns=%d summary_present=%s summary_len=%d",
        payload.chat_id, len(prior_snapshot), bool(existing_summary), len(existing_summary or ""),
    )

    conversation_context = _context_block_with_summary(prior_snapshot, existing_summary)
    if conversation_context:
        successful_turns = sum(1 for e in prior_snapshot if e.get("pipeline_success", True))
        logger.debug(
            "CONTEXT_INJECT chat_id=%s context_len=%d successful_turns=%d/%d",
            payload.chat_id, len(conversation_context), successful_turns, len(prior_snapshot),
        )

    metadata = {
        "domain": payload.domain,
        "sub_domain": payload.subdomain,
        "geography": payload.geography,
        "request_id": request_id,
        "conversation_context": conversation_context,
    }

    # ── Phase 2: run full pipeline (guardrail → intent classifier via LangGraph) ──
    pipeline_result = await run_guardrail_pipeline(
        prompt=payload.prompt,
        guardrails_list=request.app.state.guardrails,
        security_profile=security_profile,
        metadata=metadata,
    )

    guardrail_status  = pipeline_result.get("guardrail_status", "error")
    blocked_by        = pipeline_result.get("blocked_by")
    guardrail_message = pipeline_result.get("guardrail_message", "")
    intent_status     = pipeline_result.get("intent_status")
    intent_result     = pipeline_result.get("intent_result")
    intent_error      = pipeline_result.get("intent_error")
    queue_path        = pipeline_result.get("queue_path")
    sql_status        = pipeline_result.get("sql_status")
    sql_result        = pipeline_result.get("sql_result")
    sql_error         = pipeline_result.get("sql_error")
    valkyrie_status     = pipeline_result.get("valkyrie_status")
    valkyrie_result     = pipeline_result.get("valkyrie_result")
    valkyrie_error      = pipeline_result.get("valkyrie_error")
    synthesizer_context = pipeline_result.get("synthesizer_context")
    correction_attempt  = pipeline_result.get("correction_attempt", 0)
    correction_history  = pipeline_result.get("correction_history", [])
    spyder_status       = pipeline_result.get("spyder_status")
    spyder_result       = pipeline_result.get("spyder_result")
    spyder_error        = pipeline_result.get("spyder_error")
    raven_status        = pipeline_result.get("raven_status")
    raven_result        = pipeline_result.get("raven_result")
    raven_error         = pipeline_result.get("raven_error")
    dataflow_status     = pipeline_result.get("dataflow_status")
    dataflow_result     = pipeline_result.get("dataflow_result")
    dataflow_error      = pipeline_result.get("dataflow_error")

    # Get or create chat
    if payload.chat_id:
        chat = db.query(ChatHistory).filter(
            ChatHistory.chat_id == payload.chat_id,
            ChatHistory.user_id == current_user.user_id
        ).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
    else:
        title = payload.prompt[:60] + ("..." if len(payload.prompt) > 60 else "")
        chat = ChatHistory(user_id=current_user.user_id, title=title, is_active=True)
        db.add(chat)
        db.flush()

    # Build slm_payload for audit/storage
    slm_payload = {
        "prompt": payload.prompt,
        "guardrails": {
            "prompt_guardrails": [
                {"id": str(g.id), "name": g.policy_name, "type": g.check_type}
                for g in request.app.state.guardrails
            ],
            "response_guardrails": [],
        },
        "security_profile": security_profile,
        "metadata": metadata,
        "intent_result": intent_result,
    }

    # Save user message
    db.add(ChatMessage(chat_id=chat.chat_id, role="user", content=payload.prompt, payload=slm_payload))

    # ── Build assistant response based on pipeline outcome ──
    if guardrail_status == "blocked":
        assistant_content = (
            f"⚠️ **Prompt blocked by guardrail** — {blocked_by}\n\n"
            f"{guardrail_message}\n\n"
            f"*Please revise your prompt and try again.*"
        )
    elif guardrail_status in ("error", None):
        assistant_content = (
            f"⚠️ **Guardrail check failed** — {guardrail_message}\n\n"
            f"*Your prompt could not be processed. Please contact your administrator.*"
        )
    elif intent_status == "out_of_scope":
        assistant_content = (
            f"✅ Guardrails passed.\n\n"
            f"🔒 **Data not in your scope** — {intent_error}\n\n"
            f"*You don't have access to the data required for this query. "
            f"Contact your administrator to request access.*"
        )
    elif intent_status == "error":
        assistant_content = (
            f"✅ Guardrails passed.\n\n"
            f"⚠️ **Intent classification failed** — {intent_error}\n\n"
            f"*Please try again or contact your administrator.*"
        )
    else:
        # Full success — build intent summary
        intents = intent_result.get("intents", []) if intent_result else []
        total = intent_result.get("total_intents", len(intents)) if intent_result else 0

        intent_lines = []
        for i in intent_result.get("intents", []):
            types_str = "/".join(i.get("intent_types", []))
            source = i.get("data_source", "")
            domain = i.get("domain", "")
            sub = i.get("sub_domain", "")
            desc = i.get("description", "")
            intent_lines.append(f"  {i.get('intent_id', '?')}. [{types_str}·{source}] {domain} › {sub} — {desc}")

        intent_block = "\n".join(intent_lines) if intent_lines else "  No intents detected."

        # SQL + validation note
        if sql_status == "skipped":
            sql_note = "\n\n*No structured intents — SQL generation skipped.*"
        elif sql_status in ("success", "partial"):
            results = (sql_result or {}).get("sql_results", [])
            n_ok  = sum(1 for r in results if r.get("status") == "success")
            n_err = sum(1 for r in results if r.get("status") == "error")
            sql_note = f"\n\n✅ **SAGE generated SQL** — {n_ok} query(ies)"
            if n_err:
                sql_note += f", {n_err} failed"
            # Append VALKYRIE validation outcome
            corr_note = f" (after {correction_attempt} correction(s))" if correction_attempt > 0 else ""
            if valkyrie_status == "pass":
                sql_note += f"\n✅ **VALKYRIE validation passed**{corr_note}"
            elif valkyrie_status == "partial":
                val_results = (valkyrie_result or {}).get("validated_results", [])
                n_fail = sum(1 for r in val_results if r.get("status") == "fail")
                sql_note += f"\n⚠️ **VALKYRIE: {n_fail} query(ies) still have violations**{corr_note}"
            elif valkyrie_status == "fail":
                sql_note += f"\n⚠️ **VALKYRIE validation failed**{corr_note} — queries may not satisfy security policies"
            elif valkyrie_status == "error":
                sql_note += f"\n⚠️ **VALKYRIE unavailable** — {valkyrie_error or 'validation skipped'}"
        elif sql_status == "error":
            sql_note = f"\n\n⚠️ **SQL generation failed** — {sql_error or 'unknown error'}"
        else:
            sql_note = ""

        # RAVEN + SPYDER notes appended for ALL cases (SQL or pure-unstructured)
        if raven_status == "success":
            n_inputs = len((raven_result or {}).get("similarity_search_inputs", []))
            sql_note += f"\n✅ **RAVEN retrieved {n_inputs} RAG input(s)**"
        elif raven_status == "error":
            sql_note += f"\n⚠️ **RAVEN retrieval failed** — {raven_error or 'unknown error'}"
        if spyder_status == "success":
            sql_note += "\n✅ **SPYDER synthesis complete**"
        elif spyder_status == "error":
            sql_note += f"\n⚠️ **SPYDER synthesis failed** — {spyder_error or 'unknown error'}"

        # Pipeline tracking goes to backend logs only — chat shows synthesis result
        if spyder_status == "success":
            assistant_content = ""
        else:
            assistant_content = (
                f"✅ **Guardrails passed.** ARIA detected **{total} intent(s)**:\n\n"
                f"{intent_block}"
                f"{sql_note}"
            )

    # Build updated context snapshot (only on successful intent classification)
    context_snapshot = None
    if intent_status == "success" and intent_result:
        context_snapshot = _build_context_snapshot(
            prior_snapshot, intent_result, payload.prompt,
            pipeline_success=(spyder_status == "success"),
        )

    assistant_payload = {}
    if spyder_result:
        assistant_payload["spyder_result"] = spyder_result
    if context_snapshot:
        assistant_payload["context_snapshot"] = context_snapshot
    # Carry forward existing summary until background task updates it
    if existing_summary:
        assistant_payload["chat_summary"] = existing_summary
    if not assistant_payload:
        assistant_payload = None

    asst_msg = ChatMessage(chat_id=chat.chat_id, role="assistant", content=assistant_content, payload=assistant_payload)
    db.add(asst_msg)
    db.flush()   # get message_id before commit
    asst_msg_id = asst_msg.message_id
    db.commit()

    if context_snapshot:
        logger.info(
            "CONTEXT_SAVE chat_id=%d snapshot_turns=%d pipeline_success=%s",
            chat.chat_id, len(context_snapshot),
            context_snapshot[-1].get("pipeline_success", False) if context_snapshot else False,
        )

    # Trigger summary update when snapshot was full (eviction happened)
    if context_snapshot and len(prior_snapshot) >= _MAX_CONTEXT_TURNS:
        logger.info(
            "SUMMARY_TRIGGER chat_id=%d msg_id=%d evicting=%d turns",
            chat.chat_id, asst_msg_id, len(prior_snapshot),
        )
        background_tasks.add_task(
            _background_summary_update, chat.chat_id, asst_msg_id, prior_snapshot, existing_summary
        )

    return {
        "chat_id":             chat.chat_id,
        "request_id":         request_id,
        "guardrail_status":   guardrail_status,
        "blocked_by":         blocked_by,
        "intent_status":      intent_status,
        "intent_result":      intent_result,
        "sql_status":         sql_status,
        "sql_result":         sql_result,
        "valkyrie_status":    valkyrie_status,
        "valkyrie_result":    valkyrie_result,
        "synthesizer_context": synthesizer_context,
        "correction_attempt":  correction_attempt,
        "correction_history":  correction_history,
        "spyder_status":       spyder_status,
        "spyder_result":       spyder_result,
        "spyder_error":        spyder_error,
        "raven_status":        raven_status,
        "raven_result":        raven_result,
        "raven_error":         raven_error,
        "dataflow_status":     dataflow_status,
        "dataflow_result":     dataflow_result,
        "dataflow_error":      dataflow_error,
        "response":            assistant_content,
    }


def _node_to_sse(node: str, delta: dict, accumulated: dict) -> dict:
    base = {"type": "node", "node": node}
    if node == "guardrail_check":
        return {**base, "label": "Guardrail check",
                "status": delta.get("guardrail_status", "error"),
                "blocked_by": delta.get("blocked_by"),
                "message": delta.get("guardrail_message", "")}
    if node == "intent_classify":
        ir = delta.get("intent_result") or {}
        return {**base, "label": "Intent classification",
                "status": delta.get("intent_status", "error"),
                "intent_count": len(ir.get("intents", [])),
                "error": delta.get("intent_error")}
    if node == "sql_generate":
        sr = delta.get("sql_result") or {}
        n_ok = sum(1 for r in sr.get("sql_results", []) if r.get("status") == "success")
        return {**base, "label": "SQL generation",
                "status": delta.get("sql_status", "error"),
                "sql_count": n_ok,
                "error": delta.get("sql_error")}
    if node == "validate_sql":
        return {**base, "label": "SQL validation",
                "status": delta.get("valkyrie_status", "error"),
                "correction_attempt": accumulated.get("correction_attempt", 0),
                "error": delta.get("valkyrie_error")}
    if node == "sql_correct":
        return {**base, "label": "SQL correction",
                "attempt": delta.get("correction_attempt", 0)}
    if node == "raven_query":
        rr = delta.get("raven_result") or {}
        return {**base, "label": "RAG retrieval",
                "status": delta.get("raven_status", "error"),
                "inputs": len(rr.get("similarity_search_inputs", [])),
                "error": delta.get("raven_error")}
    if node == "spyder_synthesize":
        return {**base, "label": "Synthesis",
                "status": delta.get("spyder_status", "error"),
                "error": delta.get("spyder_error")}
    if node == "dataflow_run":
        df_status = delta.get("dataflow_status")
        df_result = delta.get("dataflow_result") or {}
        plan = df_result.get("plan") or delta.get("dataflow_plan") or {}
        n_steps = len(plan.get("steps", [])) if isinstance(plan, dict) else 0
        return {**base, "label": "Data pipeline",
                "status": df_status or "skipped",
                "steps_planned": n_steps,
                "error": delta.get("dataflow_error")}
    return base


@router.post("/send/stream")
async def stream_send_prompt(
    request: Request,
    payload: SendPromptRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.agents.orchestrator import stream_pipeline as _stream_pipeline

    request_id = str(uuid.uuid4())

    sg_ids = payload.security_group_ids or None
    sg_id  = payload.security_group_id  or None
    if sg_ids:
        security_profile = build_security_payload(db, current_user.user_id, security_group_ids=sg_ids)
    elif sg_id:
        security_profile = build_security_payload(db, current_user.user_id, security_group_id=sg_id)
    else:
        security_profile = get_cached_user_profile(db, current_user.user_id)

    # Load persistent context snapshot + rolling summary from last assistant message
    prior_snapshot_stream, existing_summary_stream = _load_context_data(db, payload.chat_id)
    logger.info(
        "CONTEXT_LOAD chat_id=%s snapshot_turns=%d summary_present=%s summary_len=%d",
        payload.chat_id, len(prior_snapshot_stream), bool(existing_summary_stream), len(existing_summary_stream or ""),
    )

    conversation_context_stream = _context_block_with_summary(prior_snapshot_stream, existing_summary_stream)
    if conversation_context_stream:
        successful_turns_stream = sum(1 for e in prior_snapshot_stream if e.get("pipeline_success", True))
        logger.debug(
            "CONTEXT_INJECT chat_id=%s context_len=%d successful_turns=%d/%d",
            payload.chat_id, len(conversation_context_stream), successful_turns_stream, len(prior_snapshot_stream),
        )

    metadata = {
        "domain":               payload.domain,
        "sub_domain":           payload.subdomain,
        "geography":            payload.geography,
        "request_id":           request_id,
        "conversation_context": conversation_context_stream,
    }

    prompt_guardrails = [
        {"id": str(g.id), "name": g.policy_name, "type": g.check_type}
        for g in request.app.state.guardrails
    ]
    guardrails_payload = {"prompt_guardrails": prompt_guardrails, "response_guardrails": []}

    # Validate existing chat before streaming so we can 404 early
    existing_chat_id = None
    if payload.chat_id:
        existing = db.query(ChatHistory).filter(
            ChatHistory.chat_id == payload.chat_id,
            ChatHistory.user_id == current_user.user_id,
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Chat not found")
        existing_chat_id = existing.chat_id

    async def _sse():
        accumulated: dict = {}

        try:
            async for node_name, delta in _stream_pipeline(
                prompt=payload.prompt,
                guardrails=guardrails_payload,
                security_profile=security_profile,
                metadata=metadata,
            ):
                accumulated.update(delta)
                yield f"data: {json.dumps(_node_to_sse(node_name, delta, accumulated))}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        # ── Unpack accumulated state ──────────────────────────────────────────
        guardrail_status  = accumulated.get("guardrail_status", "error")
        blocked_by        = accumulated.get("blocked_by")
        guardrail_message = accumulated.get("guardrail_message", "")
        intent_status     = accumulated.get("intent_status")
        intent_result     = accumulated.get("intent_result")
        intent_error      = accumulated.get("intent_error")
        sql_status        = accumulated.get("sql_status")
        sql_result        = accumulated.get("sql_result")
        sql_error         = accumulated.get("sql_error")
        valkyrie_status   = accumulated.get("valkyrie_status")
        valkyrie_result   = accumulated.get("valkyrie_result")
        valkyrie_error    = accumulated.get("valkyrie_error")
        synthesizer_context = accumulated.get("synthesizer_context")
        correction_attempt  = accumulated.get("correction_attempt", 0)
        correction_history  = accumulated.get("correction_history", [])
        spyder_status     = accumulated.get("spyder_status")
        spyder_result     = accumulated.get("spyder_result")
        spyder_error      = accumulated.get("spyder_error")
        raven_status      = accumulated.get("raven_status")
        raven_result      = accumulated.get("raven_result")
        raven_error       = accumulated.get("raven_error")
        dataflow_status   = accumulated.get("dataflow_status")
        dataflow_result   = accumulated.get("dataflow_result")
        dataflow_error    = accumulated.get("dataflow_error")

        # ── Build assistant content (mirrors /send logic) ─────────────────────
        if guardrail_status == "blocked":
            assistant_content = (
                f"⚠️ **Prompt blocked by guardrail** — {blocked_by}\n\n"
                f"{guardrail_message}\n\n"
                f"*Please revise your prompt and try again.*"
            )
        elif guardrail_status in ("error", None):
            assistant_content = (
                f"⚠️ **Guardrail check failed** — {guardrail_message}\n\n"
                f"*Your prompt could not be processed. Please contact your administrator.*"
            )
        elif intent_status == "out_of_scope":
            assistant_content = (
                f"✅ Guardrails passed.\n\n"
                f"🔒 **Data not in your scope** — {intent_error}\n\n"
                f"*You don't have access to the data required for this query. "
                f"Contact your administrator to request access.*"
            )
        elif intent_status == "error":
            assistant_content = (
                f"✅ Guardrails passed.\n\n"
                f"⚠️ **Intent classification failed** — {intent_error}\n\n"
                f"*Please try again or contact your administrator.*"
            )
        else:
            intents = intent_result.get("intents", []) if intent_result else []
            total   = intent_result.get("total_intents", len(intents)) if intent_result else 0
            intent_lines = []
            for i in (intent_result or {}).get("intents", []):
                types_str = "/".join(i.get("intent_types", []))
                intent_lines.append(
                    f"  {i.get('intent_id', '?')}. [{types_str}·{i.get('data_source','')}] "
                    f"{i.get('domain','')} › {i.get('sub_domain','')} — {i.get('description','')}"
                )
            intent_block = "\n".join(intent_lines) if intent_lines else "  No intents detected."

            if sql_status == "skipped":
                sql_note = "\n\n*No structured intents — SQL generation skipped.*"
            elif sql_status in ("success", "partial"):
                results = (sql_result or {}).get("sql_results", [])
                n_ok  = sum(1 for r in results if r.get("status") == "success")
                n_err = sum(1 for r in results if r.get("status") == "error")
                sql_note = f"\n\n✅ **SAGE generated SQL** — {n_ok} query(ies)"
                if n_err:
                    sql_note += f", {n_err} failed"
                corr_note = f" (after {correction_attempt} correction(s))" if correction_attempt > 0 else ""
                if valkyrie_status == "pass":
                    sql_note += f"\n✅ **VALKYRIE validation passed**{corr_note}"
                elif valkyrie_status == "partial":
                    n_fail = sum(1 for r in (valkyrie_result or {}).get("validated_results", []) if r.get("status") == "fail")
                    sql_note += f"\n⚠️ **VALKYRIE: {n_fail} query(ies) still have violations**{corr_note}"
                elif valkyrie_status == "fail":
                    sql_note += f"\n⚠️ **VALKYRIE validation failed**{corr_note}"
                elif valkyrie_status == "error":
                    sql_note += f"\n⚠️ **VALKYRIE unavailable** — {valkyrie_error or 'validation skipped'}"
            elif sql_status == "error":
                sql_note = f"\n\n⚠️ **SQL generation failed** — {sql_error or 'unknown error'}"
            else:
                sql_note = ""

            if raven_status == "success":
                n_inputs = len((raven_result or {}).get("similarity_search_inputs", []))
                sql_note += f"\n✅ **RAVEN retrieved {n_inputs} RAG input(s)**"
            elif raven_status == "error":
                sql_note += f"\n⚠️ **RAVEN retrieval failed** — {raven_error or 'unknown error'}"
            if spyder_status == "success":
                sql_note += "\n✅ **SPYDER synthesis complete**"
            elif spyder_status == "error":
                sql_note += f"\n⚠️ **SPYDER synthesis failed** — {spyder_error or 'unknown error'}"

            assistant_content = "" if spyder_status == "success" else (
                f"✅ **Guardrails passed.** ARIA detected **{total} intent(s)**:\n\n"
                f"{intent_block}{sql_note}"
            )

        # ── Save to DB ────────────────────────────────────────────────────────
        if existing_chat_id:
            chat_id_out = existing_chat_id
        else:
            title = payload.prompt[:60] + ("..." if len(payload.prompt) > 60 else "")
            chat = ChatHistory(user_id=current_user.user_id, title=title, is_active=True)
            db.add(chat)
            db.flush()
            chat_id_out = chat.chat_id

        slm_payload = {
            "prompt": payload.prompt,
            "guardrails": guardrails_payload,
            "security_profile": security_profile,
            "metadata": metadata,
            "intent_result": intent_result,
        }
        db.add(ChatMessage(chat_id=chat_id_out, role="user", content=payload.prompt, payload=slm_payload))

        # Build updated context snapshot (only on successful intent classification)
        stream_context_snapshot = None
        if intent_status == "success" and intent_result:
            stream_context_snapshot = _build_context_snapshot(
                prior_snapshot_stream, intent_result, payload.prompt,
                pipeline_success=(spyder_status == "success"),
            )

        stream_asst_payload = {}
        if spyder_result:
            stream_asst_payload["spyder_result"] = spyder_result
        if stream_context_snapshot:
            stream_asst_payload["context_snapshot"] = stream_context_snapshot
        # Carry forward existing summary until background task updates it
        if existing_summary_stream:
            stream_asst_payload["chat_summary"] = existing_summary_stream
        if not stream_asst_payload:
            stream_asst_payload = None

        stream_asst_msg = ChatMessage(chat_id=chat_id_out, role="assistant", content=assistant_content, payload=stream_asst_payload)
        db.add(stream_asst_msg)
        db.flush()
        stream_asst_msg_id = stream_asst_msg.message_id
        db.commit()

        if stream_context_snapshot:
            logger.info(
                "CONTEXT_SAVE chat_id=%d snapshot_turns=%d pipeline_success=%s",
                chat_id_out, len(stream_context_snapshot),
                stream_context_snapshot[-1].get("pipeline_success", False) if stream_context_snapshot else False,
            )

        # Trigger summary update when snapshot was full (eviction happened)
        if stream_context_snapshot and len(prior_snapshot_stream) >= _MAX_CONTEXT_TURNS:
            logger.info(
                "SUMMARY_TRIGGER chat_id=%d msg_id=%d evicting=%d turns",
                chat_id_out, stream_asst_msg_id, len(prior_snapshot_stream),
            )
            import asyncio
            asyncio.create_task(
                _background_summary_update(chat_id_out, stream_asst_msg_id, prior_snapshot_stream, existing_summary_stream)
            )

        done_payload = {
            "type": "done", "chat_id": chat_id_out, "request_id": request_id,
            "guardrail_status": guardrail_status, "blocked_by": blocked_by,
            "intent_status": intent_status, "intent_result": intent_result,
            "sql_status": sql_status, "sql_result": sql_result,
            "valkyrie_status": valkyrie_status, "valkyrie_result": valkyrie_result,
            "synthesizer_context": synthesizer_context,
            "correction_attempt": correction_attempt, "correction_history": correction_history,
            "spyder_status": spyder_status, "spyder_result": spyder_result, "spyder_error": spyder_error,
            "raven_status": raven_status, "raven_result": raven_result, "raven_error": raven_error,
            "dataflow_status": dataflow_status, "dataflow_result": dataflow_result, "dataflow_error": dataflow_error,
            "response": assistant_content,
        }
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.delete("/{chat_id}")
def delete_chat(chat_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(ChatHistory).filter(
        ChatHistory.chat_id == chat_id,
        ChatHistory.user_id == current_user.user_id
    ).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Not found")
    chat.is_active = False
    db.commit()
    return {"message": "Deleted"}
