from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.core.security import get_current_user, get_password_hash
from pydantic import BaseModel

class ResetPasswordRequest(BaseModel):
    new_password: str
from app.models.user import User, UserRole, Role, UserSecurityGroup, SecurityGroup
from app.schemas.schemas import UserCreate, UserUpdate, MessageResponse

def invalidate_user_cache(user_id):
    from app.api.routes.chat import invalidate_user_profile_cache
    invalidate_user_profile_cache(user_id)

router = APIRouter()


def check_admin(current_user, db):
    ur = db.query(UserRole).filter(UserRole.user_id == current_user.user_id, UserRole.is_active == True).first()
    if not ur:
        raise HTTPException(status_code=403, detail="Admin only")
    role = db.query(Role).filter(Role.role_id == ur.role_id).first()
    if not role or role.role_name != "Admin":
        raise HTTPException(status_code=403, detail="Admin only")


def enrich_user(user: User, db: Session) -> dict:
    ur = db.query(UserRole).filter(UserRole.user_id == user.user_id, UserRole.is_active == True).first()
    role_name = None
    if ur:
        role = db.query(Role).filter(Role.role_id == ur.role_id).first()
        role_name = role.role_name if role else None
    sgs = db.query(SecurityGroup).join(UserSecurityGroup).filter(
        UserSecurityGroup.user_id == user.user_id,
        UserSecurityGroup.is_active == True,
        SecurityGroup.is_active == True,
    ).all()
    return {
        "UserID": user.user_id,
        "FirstName": user.first_name,
        "LastName": user.last_name,
        "Email": user.email,
        "Contact": user.contact,
        "IsActive": user.is_active,
        "CreatedDate": user.created_date,
        "role": role_name,
        "security_groups": [{"SecurityGroupID": g.security_group_id, "SecurityGroupName": g.security_group_name} for g in sgs],
    }


@router.get("/", response_model=List[dict])
def list_users(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    users = db.query(User).all()
    return [enrich_user(u, db) for u in users]


@router.post("/", response_model=dict)
def create_user(payload: UserCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    existing = db.query(User).filter(User.email == payload.Email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        first_name=payload.FirstName,
        last_name=payload.LastName,
        email=payload.Email,
        contact=payload.Contact,
        password_hash=get_password_hash(payload.Password),
        is_active=True,
        created_by=current_user.user_id,
    )
    db.add(user)
    db.flush()
    ur = UserRole(user_id=user.user_id, role_id=payload.RoleID, is_active=True, created_by=current_user.user_id)
    db.add(ur)
    db.commit()
    db.refresh(user)
    return enrich_user(user, db)


@router.put("/{user_id}", response_model=dict)
def update_user(user_id: int, payload: UserUpdate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        if field == "RoleID":
            ur = db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.is_active == True).first()
            if ur:
                ur.role_id = val
            else:
                db.add(UserRole(user_id=user_id, role_id=val, is_active=True, created_by=current_user.user_id))
        elif field == "FirstName":
            user.first_name = val
        elif field == "LastName":
            user.last_name = val
        elif field == "IsActive":
            user.is_active = val
        elif field == "Contact":
            user.contact = val
    db.commit()
    db.refresh(user)
    invalidate_user_cache(user_id)
    return enrich_user(user, db)


@router.post("/{user_id}/reset-password", response_model=MessageResponse)
def reset_user_password(user_id: int, payload: ResetPasswordRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    return {"message": "Password reset successfully"}


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(user_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"message": "User deactivated"}


@router.post("/{user_id}/security-groups/{sg_id}", response_model=MessageResponse)
def assign_security_group(user_id: int, sg_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    existing = db.query(UserSecurityGroup).filter(
        UserSecurityGroup.user_id == user_id,
        UserSecurityGroup.security_group_id == sg_id
    ).first()
    if existing:
        existing.is_active = True
    else:
        db.add(UserSecurityGroup(user_id=user_id, security_group_id=sg_id, is_active=True, created_by=current_user.user_id))
    db.commit()
    invalidate_user_cache(user_id)
    return {"message": "Security group assigned"}


@router.get("/{user_id}/security-groups")
def get_user_security_groups(user_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.user import SecurityGroup
    groups = db.query(SecurityGroup).join(UserSecurityGroup).filter(
        UserSecurityGroup.user_id == user_id,
        UserSecurityGroup.is_active == True,
        SecurityGroup.is_active == True,
    ).all()
    return [{"SecurityGroupID": g.security_group_id, "SecurityGroupName": g.security_group_name} for g in groups]


@router.delete("/{user_id}/security-groups/{sg_id}", response_model=MessageResponse)
def remove_security_group(user_id: int, sg_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    check_admin(current_user, db)
    usg = db.query(UserSecurityGroup).filter(
        UserSecurityGroup.user_id == user_id,
        UserSecurityGroup.security_group_id == sg_id,
    ).first()
    if not usg:
        raise HTTPException(status_code=404, detail="Assignment not found")
    usg.is_active = False
    db.commit()
    invalidate_user_cache(user_id)
    return {"message": "Security group removed"}
