import uuid
import json
import time
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import (
    ChatHistory, ChatMessage, SLMConfig, PromptPolicy, PromptPolicyCheck,
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


def safe_json(obj):
    """JSON serializer that handles UUID and other non-serializable types."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def json_dumps(obj):
    return json.dumps(obj, default=safe_json, indent=2)


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


def apply_guardrails(db, prompt, request_id, fastapi_app):
    policies = fastapi_app.state.guardrails

    final_action = "allow"
    for policy in policies:
        matched, reason = False, None
        check_val = policy.check_value or {}

        if policy.check_type == "keyword_block":
            for kw in check_val.get("keywords", []):
                if kw.lower() in prompt.lower():
                    matched, reason = True, f"Keyword '{kw}' detected"
                    break
        elif policy.check_type == "max_length":
            max_len = check_val.get("max_length", 1000)
            if len(prompt) > max_len:
                matched, reason = True, f"Prompt exceeds max length {max_len}"
        elif policy.check_type == "regex":
            import re
            pattern = check_val.get("pattern", "")
            if pattern and re.search(pattern, prompt, re.IGNORECASE):
                matched, reason = True, "Pattern matched"
        elif policy.check_type == "context":
            forbidden = check_val.get("forbidden_topics", [])
            for topic in forbidden:
                if topic.lower() in prompt.lower():
                    matched, reason = True, f"Forbidden topic '{topic}' detected"
                    break

        if matched and policy.action in ("block", "escalate"):
            final_action = policy.action

        db.add(PromptPolicyCheck(
            request_id=uuid.UUID(request_id),
            policy_id=policy.id,
            matched=matched,
            action_taken=policy.action if matched else "pass",
            reason=reason,
            prompt=prompt[:500] if prompt else None,
        ))

    db.commit()
    return {"action": final_action}


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

    guardrail_result = apply_guardrails(db, payload.prompt, request_id, request.app)
    if guardrail_result["action"] == "block":
        raise HTTPException(status_code=400, detail="Prompt blocked by guardrails")

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

    # Build security profile — use provided SG list, single SG, or all assigned
    sg_ids = payload.security_group_ids or None
    sg_id = payload.security_group_id or None
    if sg_ids:
        security_profile = build_security_payload(db, current_user.user_id, security_group_ids=sg_ids)
    elif sg_id:
        security_profile = build_security_payload(db, current_user.user_id, security_group_id=sg_id)
    else:
        security_profile = get_cached_user_profile(db, current_user.user_id)

    # Guardrails list (UUID → str)
    prompt_guardrails = [
        {"id": str(g.id), "name": g.policy_name, "type": g.check_type}
        for g in request.app.state.guardrails
    ]

    slm_payload = {
        "prompt": payload.prompt,
        "guardrails": {"prompt_guardrails": prompt_guardrails, "response_guardrails": []},
        "security_profile": security_profile,
        "metadata": {
            "domain": payload.domain,
            "sub_domain": payload.subdomain,
            "geography": payload.geography,
            "request_id": request_id,
        }
    }

    # Save user message
    db.add(ChatMessage(chat_id=chat.chat_id, role="user", content=payload.prompt, payload=slm_payload))

    # Call LLM
    from app.core.config import settings as app_settings
    slm_config = db.query(SLMConfig).filter(SLMConfig.is_active == True).first()
    api_key = app_settings.LLM_API_KEY or (slm_config.api_key if slm_config else None)
    base_url = app_settings.LLM_BASE_URL or (slm_config.base_url if slm_config else None)
    model = app_settings.LLM_MODEL

    if api_key and base_url:
        try:
            # Build system prompt with context guardrail restrictions
            context_policies = db.query(PromptPolicy).filter(
                PromptPolicy.is_active == True,
                PromptPolicy.check_type == "context"
            ).order_by(PromptPolicy.priority).all()

            system_lines = [
                "You are a data assistant. You ONLY answer questions based on data from the connected database.",
                "Refuse any question that is not related to the database or its data.",
                "If asked something outside your scope, respond: 'I can only answer questions about data in the connected database.'",
            ]
            for cp in context_policies:
                cv = cp.check_value or {}
                if cv.get("description"):
                    system_lines.append(cv["description"])
                if cv.get("forbidden_topics"):
                    system_lines.append(f"Do NOT answer questions about: {', '.join(cv['forbidden_topics'])}")
            system_lines.append(f"Security profile: {json.dumps(security_profile)}")
            system_content = "\n".join(system_lines)

            llm_request = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": payload.prompt}
                ]
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(base_url, json=llm_request, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                })
                resp.raise_for_status()
                assistant_content = resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            assistant_content = f"[LLM Error {e.response.status_code}]: {error_body}"
        except Exception as e:
            assistant_content = f"[LLM Error: {str(e)}]\n\n```json\n{json_dumps(slm_payload)}\n```"
    else:
        assistant_content = f"**No LLM API key configured.** Add LLM_API_KEY to .env\n\n```json\n{json_dumps(slm_payload)}\n```"

    db.add(ChatMessage(chat_id=chat.chat_id, role="assistant", content=assistant_content))
    db.commit()

    return {
        "chat_id": chat.chat_id,
        "request_id": request_id,
        "guardrail_result": guardrail_result,
        "response": assistant_content,
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
