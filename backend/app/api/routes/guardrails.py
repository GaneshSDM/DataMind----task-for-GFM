from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import PromptPolicy, UserRole, Role
from app.schemas.schemas import GuardrailCreate, MessageResponse

router = APIRouter()


def reload_guardrails_cache(db, fastapi_app):
    fastapi_app.state.guardrails = db.query(PromptPolicy).filter(
        PromptPolicy.is_active == True
    ).order_by(PromptPolicy.priority).all()


def check_admin(current_user, db):
    ur = db.query(UserRole).filter(UserRole.user_id == current_user.user_id, UserRole.is_active == True).first()
    if not ur:
        raise HTTPException(status_code=403, detail="Admin only")
    role = db.query(Role).filter(Role.role_id == ur.role_id).first()
    if not role or role.role_name != "Admin":
        raise HTTPException(status_code=403, detail="Admin only")


_GUARDRAIL_TO_DISPLAY = {'PG': 'prompt', 'RG': 'response'}
_GUARDRAIL_TO_DB     = {'prompt': 'PG', 'response': 'RG'}

def policy_to_dict(g):
    raw = (g.guardrail or 'PG').upper()
    return {
        "id": g.id, "policy_name": g.policy_name, "description": g.description,
        "check_type": (g.check_type or '').lower(), "guardrail": _GUARDRAIL_TO_DISPLAY.get(raw, 'prompt'),
        "check_value": g.check_value,
        "action": (g.action or '').lower(), "severity": (g.severity or '').lower(),
        "priority": g.priority,
        "is_active": g.is_active, "created_at": g.created_at,
    }


@router.get("/")
def list_guardrails(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return [policy_to_dict(g) for g in db.query(PromptPolicy).order_by(PromptPolicy.priority).all()]

@router.post("/")
def create_guardrail(request: Request, payload: GuardrailCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    data = payload.model_dump()
    data['guardrail'] = _GUARDRAIL_TO_DB.get(data['guardrail'].lower(), 'PG')
    data['check_type'] = data['check_type'].upper()
    data['action'] = data['action'].upper()
    data['severity'] = data['severity'].upper()
    g = PromptPolicy(**data, is_active=True, created_by=current_user.user_id)
    db.add(g)
    db.commit()
    db.refresh(g)
    reload_guardrails_cache(db, request.app)
    return policy_to_dict(g)

@router.put("/{gid}")
def update_guardrail(gid: str, request: Request, payload: GuardrailCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    g = db.query(PromptPolicy).filter(PromptPolicy.id == gid).first()
    if not g:
        raise HTTPException(status_code=404, detail="Not found")
    data = payload.model_dump()
    data['guardrail'] = _GUARDRAIL_TO_DB.get(data['guardrail'].lower(), 'PG')
    data['check_type'] = data['check_type'].upper()
    data['action'] = data['action'].upper()
    data['severity'] = data['severity'].upper()
    for field, val in data.items():
        setattr(g, field, val)
    db.commit()
    db.refresh(g)
    reload_guardrails_cache(db, request.app)
    return policy_to_dict(g)

@router.patch("/{gid}/toggle")
def toggle_guardrail(gid: str, request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    g = db.query(PromptPolicy).filter(PromptPolicy.id == gid).first()
    if not g:
        raise HTTPException(status_code=404, detail="Not found")
    g.is_active = not g.is_active
    db.commit()
    db.refresh(g)
    reload_guardrails_cache(db, request.app)
    return policy_to_dict(g)

@router.delete("/{gid}", response_model=MessageResponse)
def delete_guardrail(gid: str, request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    g = db.query(PromptPolicy).filter(PromptPolicy.id == gid).first()
    if not g:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(g)
    db.commit()
    reload_guardrails_cache(db, request.app)
    return {"message": "Deleted"}
