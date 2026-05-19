from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import (
    SecurityGroup, SecurityGroupDomain, SecurityGroupSubDomain,
    SecurityGroupGeography, SecurityGroupRLS, SecurityGroupCLS,
    RowLevelSecurity, RLSCondition, ColumnLevelSecurity, ColumnSecurityMapping,
    UserRole, Role, UserSecurityGroup
)
from app.schemas.schemas import SecurityGroupCreate, RLSCreate, CLSCreate, MessageResponse

sg_router = APIRouter()
rls_router = APIRouter()
cls_router = APIRouter()


def invalidate_users_for_sg(db, sg_id):
    from app.api.routes.chat import invalidate_user_profile_cache
    user_ids = [usg.user_id for usg in db.query(UserSecurityGroup).filter(
        UserSecurityGroup.security_group_id == sg_id,
        UserSecurityGroup.is_active == True
    ).all()]
    for uid in user_ids:
        invalidate_user_profile_cache(uid)


def invalidate_users_for_rls(db, rls_id):
    from app.api.routes.chat import invalidate_user_profile_cache
    sg_ids = [sgr.security_group_id for sgr in db.query(SecurityGroupRLS).filter(
        SecurityGroupRLS.rls_id == rls_id
    ).all()]
    for sg_id in sg_ids:
        invalidate_users_for_sg(db, sg_id)


def invalidate_users_for_cls(db, cls_id):
    from app.api.routes.chat import invalidate_user_profile_cache
    sg_ids = [sgc.security_group_id for sgc in db.query(SecurityGroupCLS).filter(
        SecurityGroupCLS.cls_id == cls_id
    ).all()]
    for sg_id in sg_ids:
        invalidate_users_for_sg(db, sg_id)


def check_admin(current_user, db):
    ur = db.query(UserRole).filter(UserRole.user_id == current_user.user_id, UserRole.is_active == True).first()
    if not ur:
        raise HTTPException(status_code=403, detail="Admin only")
    role = db.query(Role).filter(Role.role_id == ur.role_id).first()
    if not role or role.role_name != "Admin":
        raise HTTPException(status_code=403, detail="Admin only")


def sg_to_dict(sg, db):
    return {
        "SecurityGroupID": sg.security_group_id,
        "SecurityGroupName": sg.security_group_name,
        "IsActive": sg.is_active,
        "CreatedDate": sg.created_date,
        "domain_ids": [r.domain_id for r in db.query(SecurityGroupDomain).filter(SecurityGroupDomain.security_group_id == sg.security_group_id, SecurityGroupDomain.is_active == True).all()],
        "subdomain_ids": [r.sub_domain_id for r in db.query(SecurityGroupSubDomain).filter(SecurityGroupSubDomain.security_group_id == sg.security_group_id, SecurityGroupSubDomain.is_active == True).all()],
        "geo_ids": [r.geo_id for r in db.query(SecurityGroupGeography).filter(SecurityGroupGeography.security_group_id == sg.security_group_id, SecurityGroupGeography.is_active == True).all()],
        "rls_ids": [r.rls_id for r in db.query(SecurityGroupRLS).filter(SecurityGroupRLS.security_group_id == sg.security_group_id, SecurityGroupRLS.is_active == True).all()],
        "cls_ids": [r.cls_id for r in db.query(SecurityGroupCLS).filter(SecurityGroupCLS.security_group_id == sg.security_group_id, SecurityGroupCLS.is_active == True).all()],
    }


# ── Security Groups ───────────────────────────────────────────────────────────
@sg_router.get("/")
def list_security_groups(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return [sg_to_dict(sg, db) for sg in db.query(SecurityGroup).filter(SecurityGroup.is_active == True).all()]

@sg_router.get("/{sg_id}")
def get_security_group(sg_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    sg = db.query(SecurityGroup).filter(SecurityGroup.security_group_id == sg_id).first()
    if not sg:
        raise HTTPException(status_code=404, detail="Not found")
    return sg_to_dict(sg, db)

@sg_router.post("/")
def create_security_group(payload: SecurityGroupCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    sg = SecurityGroup(security_group_name=payload.SecurityGroupName, is_active=True, created_by=current_user.user_id)
    db.add(sg)
    db.flush()
    for did in payload.domain_ids:
        db.add(SecurityGroupDomain(security_group_id=sg.security_group_id, domain_id=did, is_active=True, created_by=current_user.user_id))
    for sdid in payload.subdomain_ids:
        db.add(SecurityGroupSubDomain(security_group_id=sg.security_group_id, sub_domain_id=sdid, is_active=True, created_by=current_user.user_id))
    for gid in payload.geo_ids:
        db.add(SecurityGroupGeography(security_group_id=sg.security_group_id, geo_id=gid, is_active=True, created_by=current_user.user_id))
    for rid in payload.rls_ids:
        db.add(SecurityGroupRLS(security_group_id=sg.security_group_id, rls_id=rid, is_active=True, created_by=current_user.user_id))
    for cid in payload.cls_ids:
        db.add(SecurityGroupCLS(security_group_id=sg.security_group_id, cls_id=cid, is_active=True, created_by=current_user.user_id))
    db.commit()
    db.refresh(sg)
    return sg_to_dict(sg, db)

@sg_router.put("/{sg_id}")
def update_security_group(sg_id: int, payload: SecurityGroupCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    sg = db.query(SecurityGroup).filter(SecurityGroup.security_group_id == sg_id).first()
    if not sg:
        raise HTTPException(status_code=404, detail="Not found")
    sg.security_group_name = payload.SecurityGroupName
    if payload.is_active is not None:
        sg.is_active = payload.is_active
    for model in [SecurityGroupDomain, SecurityGroupSubDomain, SecurityGroupGeography, SecurityGroupRLS, SecurityGroupCLS]:
        db.query(model).filter(model.security_group_id == sg_id).delete()
    for did in payload.domain_ids:
        db.add(SecurityGroupDomain(security_group_id=sg_id, domain_id=did, is_active=True, created_by=current_user.user_id))
    for sdid in payload.subdomain_ids:
        db.add(SecurityGroupSubDomain(security_group_id=sg_id, sub_domain_id=sdid, is_active=True, created_by=current_user.user_id))
    for gid in payload.geo_ids:
        db.add(SecurityGroupGeography(security_group_id=sg_id, geo_id=gid, is_active=True, created_by=current_user.user_id))
    for rid in payload.rls_ids:
        db.add(SecurityGroupRLS(security_group_id=sg_id, rls_id=rid, is_active=True, created_by=current_user.user_id))
    for cid in payload.cls_ids:
        db.add(SecurityGroupCLS(security_group_id=sg_id, cls_id=cid, is_active=True, created_by=current_user.user_id))
    db.commit()
    db.refresh(sg)
    invalidate_users_for_sg(db, sg_id)
    return sg_to_dict(sg, db)

@sg_router.delete("/{sg_id}", response_model=MessageResponse)
def delete_security_group(sg_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    sg = db.query(SecurityGroup).filter(SecurityGroup.security_group_id == sg_id).first()
    if not sg:
        raise HTTPException(status_code=404, detail="Not found")
    sg.is_active = False
    db.commit()
    invalidate_users_for_sg(db, sg_id)
    return {"message": "Deleted"}


# ── Row Level Security ────────────────────────────────────────────────────────
@rls_router.get("/")
def list_rls(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(RowLevelSecurity).all()
    result = []
    for r in items:
        conds = db.query(RLSCondition).filter(RLSCondition.rls_id == r.rls_id, RLSCondition.is_active == True).all()
        result.append({
            "RLS_ID": r.rls_id, "RLSName": r.rls_name, "TargetTable": r.target_table,
            "FilterExpression": r.filter_expression, "Description": r.description,
            "DomainID": r.domain_id, "SubDomainID": r.sub_domain_id, "IsActive": r.is_active,
            "conditions": [{"ConditionID": c.condition_id, "ColumnName": c.column_name, "Operator": c.operator,
                             "Value": c.value, "LogicalOperator": c.logical_operator, "SortOrder": c.sort_order} for c in conds]
        })
    return result

@rls_router.post("/")
def create_rls(payload: RLSCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    rls = RowLevelSecurity(
        rls_name=payload.RLSName, target_table=payload.TargetTable,
        filter_expression=payload.FilterExpression, description=payload.Description,
        domain_id=payload.DomainID, sub_domain_id=payload.SubDomainID,
        is_active=True, created_by=current_user.user_id
    )
    db.add(rls)
    db.flush()
    for c in (payload.conditions or []):
        db.add(RLSCondition(rls_id=rls.rls_id, column_name=c.ColumnName, operator=c.Operator,
                             value=c.Value, logical_operator=c.LogicalOperator, sort_order=c.SortOrder, is_active=True))
    db.commit()
    db.refresh(rls)
    conds = db.query(RLSCondition).filter(RLSCondition.rls_id == rls.rls_id).all()
    return {
        "RLS_ID": rls.rls_id, "RLSName": rls.rls_name, "TargetTable": rls.target_table,
        "FilterExpression": rls.filter_expression, "Description": rls.description,
        "DomainID": rls.domain_id, "SubDomainID": rls.sub_domain_id, "IsActive": rls.is_active,
        "conditions": [{"ConditionID": c.condition_id, "ColumnName": c.column_name, "Operator": c.operator,
                         "Value": c.value, "LogicalOperator": c.logical_operator, "SortOrder": c.sort_order} for c in conds]
    }

@rls_router.put("/{rls_id}")
def update_rls(rls_id: int, payload: RLSCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    rls = db.query(RowLevelSecurity).filter(RowLevelSecurity.rls_id == rls_id).first()
    if not rls:
        raise HTTPException(status_code=404, detail="Not found")
    rls.rls_name = payload.RLSName
    rls.target_table = payload.TargetTable
    rls.filter_expression = payload.FilterExpression
    rls.description = payload.Description
    if payload.IsActive is not None:
        rls.is_active = payload.IsActive
    db.commit()
    db.refresh(rls)
    invalidate_users_for_rls(db, rls_id)
    conds = db.query(RLSCondition).filter(RLSCondition.rls_id == rls.rls_id, RLSCondition.is_active == True).all()
    return {
        "RLS_ID": rls.rls_id, "RLSName": rls.rls_name, "TargetTable": rls.target_table,
        "FilterExpression": rls.filter_expression, "Description": rls.description,
        "DomainID": rls.domain_id, "SubDomainID": rls.sub_domain_id, "IsActive": rls.is_active,
        "conditions": [{"ConditionID": c.condition_id, "ColumnName": c.column_name, "Operator": c.operator,
                         "Value": c.value, "LogicalOperator": c.logical_operator, "SortOrder": c.sort_order} for c in conds]
    }

@rls_router.delete("/{rls_id}", response_model=MessageResponse)
def delete_rls(rls_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    rls = db.query(RowLevelSecurity).filter(RowLevelSecurity.rls_id == rls_id).first()
    if not rls:
        raise HTTPException(status_code=404, detail="Not found")
    rls.is_active = False
    db.commit()
    invalidate_users_for_rls(db, rls_id)
    return {"message": "Deleted"}


# ── Column Level Security ─────────────────────────────────────────────────────
@cls_router.get("/")
def list_cls(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(ColumnLevelSecurity).all()
    result = []
    for c in items:
        cols = db.query(ColumnSecurityMapping).filter(ColumnSecurityMapping.cls_id == c.cls_id, ColumnSecurityMapping.is_active == True).all()
        result.append({
            "CLS_ID": c.cls_id, "CLSName": c.cls_name, "TargetTable": c.target_table,
            "DomainID": c.domain_id, "SubDomainID": c.sub_domain_id, "IsActive": c.is_active,
            "column_mappings": [{"MappingID": cm.mapping_id, "ColumnName": cm.column_name, "CanRead": cm.can_read, "CanWrite": cm.can_write, "IsActive": cm.is_active} for cm in cols]
        })
    return result

@cls_router.post("/")
def create_cls(payload: CLSCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    cls = ColumnLevelSecurity(
        cls_name=payload.CLSName, target_table=payload.TargetTable,
        domain_id=payload.DomainID, sub_domain_id=payload.SubDomainID,
        is_active=True, created_by=current_user.user_id
    )
    db.add(cls)
    db.flush()
    for col in (payload.columns or []):
        db.add(ColumnSecurityMapping(cls_id=cls.cls_id, column_name=col.ColumnName,
                                      can_read=col.CanRead, can_write=col.CanWrite,
                                      is_active=True, created_by=current_user.user_id))
    db.commit()
    db.refresh(cls)
    cols = db.query(ColumnSecurityMapping).filter(ColumnSecurityMapping.cls_id == cls.cls_id).all()
    return {
        "CLS_ID": cls.cls_id, "CLSName": cls.cls_name, "TargetTable": cls.target_table,
        "DomainID": cls.domain_id, "SubDomainID": cls.sub_domain_id, "IsActive": cls.is_active,
        "column_mappings": [{"MappingID": cm.mapping_id, "ColumnName": cm.column_name, "CanRead": cm.can_read, "CanWrite": cm.can_write, "IsActive": cm.is_active} for cm in cols]
    }

@cls_router.put("/{cls_id}")
def update_cls(cls_id: int, payload: CLSCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    cls = db.query(ColumnLevelSecurity).filter(ColumnLevelSecurity.cls_id == cls_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Not found")
    cls.cls_name = payload.CLSName
    cls.target_table = payload.TargetTable
    if payload.IsActive is not None:
        cls.is_active = payload.IsActive
    if payload.columns is not None:
        db.query(ColumnSecurityMapping).filter(ColumnSecurityMapping.cls_id == cls_id).delete()
        for col in payload.columns:
            db.add(ColumnSecurityMapping(cls_id=cls_id, column_name=col.ColumnName,
                                          can_read=col.CanRead, can_write=col.CanWrite,
                                          is_active=True, created_by=current_user.user_id))
    db.commit()
    db.refresh(cls)
    invalidate_users_for_cls(db, cls_id)
    cols = db.query(ColumnSecurityMapping).filter(ColumnSecurityMapping.cls_id == cls.cls_id, ColumnSecurityMapping.is_active == True).all()
    return {
        "CLS_ID": cls.cls_id, "CLSName": cls.cls_name, "TargetTable": cls.target_table,
        "DomainID": cls.domain_id, "SubDomainID": cls.sub_domain_id, "IsActive": cls.is_active,
        "column_mappings": [{"MappingID": cm.mapping_id, "ColumnName": cm.column_name, "CanRead": cm.can_read, "CanWrite": cm.can_write, "IsActive": cm.is_active} for cm in cols]
    }

@cls_router.delete("/{cls_id}", response_model=MessageResponse)
def delete_cls(cls_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    cls = db.query(ColumnLevelSecurity).filter(ColumnLevelSecurity.cls_id == cls_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Not found")
    cls.is_active = False
    db.commit()
    invalidate_users_for_cls(db, cls_id)
    return {"message": "Deleted"}
