from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import SLMConfig, DBConnection, UserRole, Role
from app.schemas.schemas import SLMConfigCreate, DBConnectionCreate, MessageResponse

slm_router = APIRouter()
db_router = APIRouter()


def check_admin(current_user, db):
    ur = db.query(UserRole).filter(UserRole.user_id == current_user.user_id, UserRole.is_active == True).first()
    if not ur:
        raise HTTPException(status_code=403, detail="Admin only")
    role = db.query(Role).filter(Role.role_id == ur.role_id).first()
    if not role or role.role_name != "Admin":
        raise HTTPException(status_code=403, detail="Admin only")


@slm_router.get("/")
def list_slm_configs(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    configs = db.query(SLMConfig).filter(SLMConfig.is_active == True).all()
    return [{"ConfigID": c.config_id, "BaseURL": c.base_url, "TimeoutSeconds": c.timeout_seconds,
             "MaxRetries": c.max_retries, "ExtraHeaders": c.extra_headers, "IsActive": c.is_active} for c in configs]

@slm_router.post("/")
def create_slm_config(payload: SLMConfigCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    db.query(SLMConfig).filter(SLMConfig.is_active == True).update({"is_active": False})
    config = SLMConfig(base_url=payload.BaseURL, api_key=payload.APIKey,
                        timeout_seconds=payload.TimeoutSeconds, max_retries=payload.MaxRetries,
                        extra_headers=payload.ExtraHeaders, is_active=True, created_by=current_user.user_id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"ConfigID": config.config_id, "BaseURL": config.base_url, "TimeoutSeconds": config.timeout_seconds,
            "MaxRetries": config.max_retries, "ExtraHeaders": config.extra_headers, "IsActive": config.is_active}

@slm_router.put("/{config_id}")
def update_slm_config(config_id: int, payload: SLMConfigCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    config = db.query(SLMConfig).filter(SLMConfig.config_id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    config.base_url = payload.BaseURL
    config.api_key = payload.APIKey
    config.timeout_seconds = payload.TimeoutSeconds
    config.max_retries = payload.MaxRetries
    config.extra_headers = payload.ExtraHeaders
    db.commit()
    db.refresh(config)
    return {"ConfigID": config.config_id, "BaseURL": config.base_url, "IsActive": config.is_active}

@slm_router.post("/test")
async def test_slm(payload: SLMConfigCreate, current_user=Depends(get_current_user)):
    import httpx
    try:
        headers = {"Content-Type": "application/json"}
        if payload.APIKey:
            headers["Authorization"] = f"Bearer {payload.APIKey}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(payload.BaseURL, headers=headers)
            return {"status": "ok", "http_status": r.status_code}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@db_router.get("/")
def list_connections(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conns = db.query(DBConnection).filter(DBConnection.is_active == True).all()
    return [{"ConnectionID": c.connection_id, "ConnectionName": c.connection_name, "Host": c.host,
             "Port": c.port, "DatabaseName": c.database_name, "Username": c.username,
             "IsActive": c.is_active, "CreatedDate": c.created_date} for c in conns]

@db_router.post("/")
def create_connection(payload: DBConnectionCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    conn = DBConnection(
        connection_name=payload.ConnectionName, host=payload.Host, port=payload.Port,
        database_name=payload.DatabaseName, username=payload.Username,
        password_encrypted=payload.Password, is_active=True, created_by=current_user.user_id
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return {"ConnectionID": conn.connection_id, "ConnectionName": conn.connection_name,
            "Host": conn.host, "Port": conn.port, "DatabaseName": conn.database_name,
            "Username": conn.username, "IsActive": conn.is_active, "CreatedDate": conn.created_date}

@db_router.post("/test")
async def test_connection(payload: DBConnectionCreate):
    try:
        import psycopg2
        conn = psycopg2.connect(host=payload.Host, port=payload.Port, dbname=payload.DatabaseName,
                                 user=payload.Username, password=payload.Password, connect_timeout=5)
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@db_router.delete("/{conn_id}", response_model=MessageResponse)
def delete_connection(conn_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    conn = db.query(DBConnection).filter(DBConnection.connection_id == conn_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Not found")
    conn.is_active = False
    db.commit()
    return {"message": "Deleted"}
