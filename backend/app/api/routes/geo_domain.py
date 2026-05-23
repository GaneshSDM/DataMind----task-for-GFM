import os
import sys
import subprocess
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import Geography, Domain, SubDomain, UserRole, Role, SecurityGroupDomain, SecurityGroupSubDomain, SecurityGroupGeography, UserSecurityGroup
from app.schemas.schemas import GeoCreate, DomainCreate, SubDomainCreate, MessageResponse

logger = logging.getLogger("geo_domain")

# Path to bootstrap_schema.py — resolved from this file's location
_BOOTSTRAP_SCRIPT = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "../../../../Agents/IntentClassifier/bootstrap_schema.py",
    )
)
_ARIA_URL  = "http://localhost:8002"
_SAGE_URL  = "http://localhost:8003"


def _refresh_schema_background():
    """
    Background task: re-run bootstrap_schema.py then hot-reload ARIA + SAGE schemas.
    Fires after domain create/update so schema_reference.json stays current.
    """
    logger.info("Schema refresh triggered — running bootstrap_schema.py…")
    try:
        result = subprocess.run(
            [sys.executable, _BOOTSTRAP_SCRIPT],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            logger.info("bootstrap_schema.py OK")
            import httpx
            for name, url in [("ARIA", f"{_ARIA_URL}/schema/reload"), ("SAGE", f"{_SAGE_URL}/schema/reload")]:
                try:
                    httpx.post(url, timeout=10)
                    logger.info("%s schema hot-reloaded", name)
                except Exception as e:
                    logger.warning("%s reload failed (%s may not be running): %s", name, name, e)
        else:
            logger.error("bootstrap_schema.py failed:\n%s", result.stderr[-500:])
    except Exception as e:
        logger.error("Schema refresh error: %s", e)

geo_router = APIRouter()
domain_router = APIRouter()
subdomain_router = APIRouter()


def invalidate_users_for_geo(db, geo_id):
    from app.api.routes.chat import invalidate_user_profile_cache
    sg_ids = [sgg.security_group_id for sgg in db.query(SecurityGroupGeography).filter(
        SecurityGroupGeography.geo_id == geo_id
    ).all()]
    for sg_id in sg_ids:
        user_ids = [usg.user_id for usg in db.query(UserSecurityGroup).filter(
            UserSecurityGroup.security_group_id == sg_id,
            UserSecurityGroup.is_active == True
        ).all()]
        for uid in user_ids:
            invalidate_user_profile_cache(uid)


def invalidate_users_for_domain(db, domain_id):
    from app.api.routes.chat import invalidate_user_profile_cache
    sg_ids = [sgd.security_group_id for sgd in db.query(SecurityGroupDomain).filter(
        SecurityGroupDomain.domain_id == domain_id
    ).all()]
    for sg_id in sg_ids:
        user_ids = [usg.user_id for usg in db.query(UserSecurityGroup).filter(
            UserSecurityGroup.security_group_id == sg_id,
            UserSecurityGroup.is_active == True
        ).all()]
        for uid in user_ids:
            invalidate_user_profile_cache(uid)


def invalidate_users_for_subdomain(db, subdomain_id):
    from app.api.routes.chat import invalidate_user_profile_cache
    sg_ids = [sgsd.security_group_id for sgsd in db.query(SecurityGroupSubDomain).filter(
        SecurityGroupSubDomain.sub_domain_id == subdomain_id
    ).all()]
    for sg_id in sg_ids:
        user_ids = [usg.user_id for usg in db.query(UserSecurityGroup).filter(
            UserSecurityGroup.security_group_id == sg_id,
            UserSecurityGroup.is_active == True
        ).all()]
        for uid in user_ids:
            invalidate_user_profile_cache(uid)


def check_admin(current_user, db):
    ur = db.query(UserRole).filter(UserRole.user_id == current_user.user_id, UserRole.is_active == True).first()
    if not ur:
        raise HTTPException(status_code=403, detail="Admin only")
    role = db.query(Role).filter(Role.role_id == ur.role_id).first()
    if not role or role.role_name != "Admin":
        raise HTTPException(status_code=403, detail="Admin only")


# ── Geography ─────────────────────────────────────────────────────────────────
@geo_router.get("/")
def list_geographies(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Geography).all()
    return [{"GeoID": r.geo_id, "GeoName": r.geo_name, "IsActive": r.is_active, "CreatedDate": r.created_date} for r in rows]

@geo_router.post("/")
def create_geography(payload: GeoCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    geo = Geography(geo_name=payload.GeoName, is_active=True, created_by=current_user.user_id)
    db.add(geo)
    db.commit()
    db.refresh(geo)
    return {"GeoID": geo.geo_id, "GeoName": geo.geo_name, "IsActive": geo.is_active, "CreatedDate": geo.created_date}

@geo_router.put("/{geo_id}")
def update_geography(geo_id: int, payload: GeoCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    geo = db.query(Geography).filter(Geography.geo_id == geo_id).first()
    if not geo:
        raise HTTPException(status_code=404, detail="Not found")
    geo.geo_name = payload.GeoName
    if payload.IsActive is not None:
        geo.is_active = payload.IsActive
    db.commit()
    db.refresh(geo)
    invalidate_users_for_geo(db, geo_id)
    return {"GeoID": geo.geo_id, "GeoName": geo.geo_name, "IsActive": geo.is_active, "CreatedDate": geo.created_date}

@geo_router.delete("/{geo_id}", response_model=MessageResponse)
def delete_geography(geo_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    geo = db.query(Geography).filter(Geography.geo_id == geo_id).first()
    if not geo:
        raise HTTPException(status_code=404, detail="Not found")
    geo.is_active = False
    db.commit()
    invalidate_users_for_geo(db, geo_id)
    return {"message": "Deleted"}


# ── Domain ────────────────────────────────────────────────────────────────────
def _domain_row(d) -> dict:
    return {
        "DomainID":   d.domain_id,
        "DomainName": d.domain_name,
        "DbSchema":   d.db_schema,
        "IsActive":   d.is_active,
        "CreatedDate": d.created_date,
    }


@domain_router.get("/schemas")
def list_pg_schemas(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Return all user-created PostgreSQL schemas (excludes pg_*, information_schema, public if empty)."""
    check_admin(current_user, db)
    result = db.execute(text(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('information_schema', 'public')
          AND schema_name NOT LIKE 'pg_%'
        ORDER BY schema_name
        """
    ))
    return [{"value": row[0], "label": row[0]} for row in result.fetchall()]


@domain_router.get("/")
def list_domains(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return [_domain_row(r) for r in db.query(Domain).all()]


@domain_router.post("/")
def create_domain(
    payload: DomainCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_admin(current_user, db)
    d = Domain(
        domain_name=payload.DomainName,
        db_schema=payload.DbSchema or None,
        is_active=True,
        created_by=current_user.user_id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    if d.db_schema:
        background_tasks.add_task(_refresh_schema_background)
    return _domain_row(d)


@domain_router.put("/{domain_id}")
def update_domain(
    domain_id: int,
    payload: DomainCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_admin(current_user, db)
    d = db.query(Domain).filter(Domain.domain_id == domain_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    d.domain_name = payload.DomainName
    if payload.DbSchema is not None:
        d.db_schema = payload.DbSchema or None
    if payload.IsActive is not None:
        d.is_active = payload.IsActive
    db.commit()
    db.refresh(d)
    invalidate_users_for_domain(db, domain_id)
    background_tasks.add_task(_refresh_schema_background)
    return _domain_row(d)


@domain_router.delete("/{domain_id}", response_model=MessageResponse)
def delete_domain(domain_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    d = db.query(Domain).filter(Domain.domain_id == domain_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    d.is_active = False
    db.commit()
    invalidate_users_for_domain(db, domain_id)
    return {"message": "Deleted"}


# ── SubDomain ─────────────────────────────────────────────────────────────────
@subdomain_router.get("/")
def list_subdomains(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    sds = db.query(SubDomain).all()
    result = []
    for sd in sds:
        d = db.query(Domain).filter(Domain.domain_id == sd.domain_id).first()
        result.append({
            "SubDomainID": sd.sub_domain_id, "DomainID": sd.domain_id,
            "SubDomainName": sd.sub_domain_name, "IsActive": sd.is_active,
            "domain_name": d.domain_name if d else None,
        })
    return result

@subdomain_router.post("/")
def create_subdomain(payload: SubDomainCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    sd = SubDomain(domain_id=payload.DomainID, sub_domain_name=payload.SubDomainName, is_active=True, created_by=current_user.user_id)
    db.add(sd)
    db.commit()
    db.refresh(sd)
    d = db.query(Domain).filter(Domain.domain_id == sd.domain_id).first()
    return {"SubDomainID": sd.sub_domain_id, "DomainID": sd.domain_id, "SubDomainName": sd.sub_domain_name, "IsActive": sd.is_active, "domain_name": d.domain_name if d else None}

@subdomain_router.put("/{sd_id}")
def update_subdomain(sd_id: int, payload: SubDomainCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    sd = db.query(SubDomain).filter(SubDomain.sub_domain_id == sd_id).first()
    if not sd:
        raise HTTPException(status_code=404, detail="Not found")
    sd.domain_id = payload.DomainID
    sd.sub_domain_name = payload.SubDomainName
    if payload.IsActive is not None:
        sd.is_active = payload.IsActive
    db.commit()
    db.refresh(sd)
    invalidate_users_for_subdomain(db, sd_id)
    d = db.query(Domain).filter(Domain.domain_id == sd.domain_id).first()
    return {"SubDomainID": sd.sub_domain_id, "DomainID": sd.domain_id, "SubDomainName": sd.sub_domain_name, "IsActive": sd.is_active, "domain_name": d.domain_name if d else None}

@subdomain_router.delete("/{sd_id}", response_model=MessageResponse)
def delete_subdomain(sd_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    sd = db.query(SubDomain).filter(SubDomain.sub_domain_id == sd_id).first()
    if not sd:
        raise HTTPException(status_code=404, detail="Not found")
    sd.is_active = False
    db.commit()
    invalidate_users_for_subdomain(db, sd_id)
    return {"message": "Deleted"}
