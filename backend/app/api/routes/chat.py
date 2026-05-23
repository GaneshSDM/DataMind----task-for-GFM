import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Request
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
    return [{"MessageID": m.message_id, "Role": m.role, "Content": m.content, "Payload": m.payload, "CreatedDate": m.created_date} for m in msgs]


@router.post("/send")
async def send_prompt(request: Request, payload: SendPromptRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
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

    metadata = {
        "domain": payload.domain,
        "sub_domain": payload.subdomain,
        "geography": payload.geography,
        "request_id": request_id,
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
            # SPYDER synthesis note
            if spyder_status == "success":
                sql_note += "\n✅ **SPYDER synthesis complete**"
            elif spyder_status == "error":
                sql_note += f"\n⚠️ **SPYDER synthesis failed** — {spyder_error or 'unknown error'}"
        elif sql_status == "error":
            sql_note = f"\n\n⚠️ **SQL generation failed** — {sql_error or 'unknown error'}"
        else:
            sql_note = ""

        assistant_content = (
            f"✅ **Guardrails passed.** ARIA detected **{total} intent(s)**:\n\n"
            f"{intent_block}"
            f"{sql_note}"
        )

    db.add(ChatMessage(chat_id=chat.chat_id, role="assistant", content=assistant_content))
    db.commit()

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
        "response":            assistant_content,
    }


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
