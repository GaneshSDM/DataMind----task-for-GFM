"""
Agent configuration routes.
GET  /api/agents/statuses  — ping all agent health endpoints (authenticated)
GET  /api/agents           — list all agents (authenticated)
GET  /api/agents/{name}    — single agent by agent_name (authenticated)
PUT  /api/agents/{name}    — update config blob (admin only)
"""
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import AgentConfig, UserRole, Role
from app.schemas.schemas import AgentConfigUpdate, AgentConfigResponse

router = APIRouter()


def _check_admin(current_user, db: Session):
    ur = db.query(UserRole).filter(
        UserRole.user_id == current_user.user_id,
        UserRole.is_active == True,
    ).first()
    if not ur:
        raise HTTPException(status_code=403, detail="Admin only")
    role = db.query(Role).filter(Role.role_id == ur.role_id).first()
    if not role or role.role_name != "Admin":
        raise HTTPException(status_code=403, detail="Admin only")


def _to_dict(ag: AgentConfig) -> dict:
    return {
        "agent_id":     ag.agent_id,
        "agent_name":   ag.agent_name,
        "display_name": ag.display_name,
        "description":  ag.description,
        "port":         ag.port,
        "config":       ag.config or {},
        "is_active":    ag.is_active,
        "updated_date": ag.updated_date,
        "updated_by":   ag.updated_by,
    }


_HEALTH_URLS = {
    "heimdall": "http://localhost:8001/health",
    "aria":     "http://localhost:8002/health",
    "sage":     "http://localhost:8003/health",
    "valkyrie": "http://localhost:8004/health",
    "spyder":   "http://localhost:8005/api/health",
    "raven":    "http://localhost:8006/health",
}


@router.get("/statuses")
async def get_agent_statuses(current_user=Depends(get_current_user)):
    """Ping every agent health endpoint; returns {agent_name: 'online'|'degraded'|'offline'}."""
    results = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in _HEALTH_URLS.items():
            try:
                r = await client.get(url)
                results[name] = "online" if r.status_code < 500 else "degraded"
            except Exception:
                results[name] = "offline"
    return results


@router.get("/", response_model=list[AgentConfigResponse])
def list_agents(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agents = (
        db.query(AgentConfig)
        .filter(AgentConfig.is_active == True)
        .order_by(AgentConfig.port)
        .all()
    )
    return [_to_dict(a) for a in agents]


@router.get("/{agent_name}", response_model=AgentConfigResponse)
def get_agent(
    agent_name: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ag = db.query(AgentConfig).filter(AgentConfig.agent_name == agent_name).first()
    if not ag:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return _to_dict(ag)


@router.put("/{agent_name}", response_model=AgentConfigResponse)
def update_agent(
    agent_name: str,
    payload: AgentConfigUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_admin(current_user, db)

    ag = db.query(AgentConfig).filter(AgentConfig.agent_name == agent_name).first()
    if not ag:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    ag.config       = payload.config
    ag.updated_by   = current_user.user_id
    ag.updated_date = datetime.now(timezone.utc)

    db.commit()
    db.refresh(ag)
    return _to_dict(ag)
