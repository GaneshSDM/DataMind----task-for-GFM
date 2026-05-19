from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import verify_password, create_access_token, get_current_user, get_password_hash
from pydantic import BaseModel

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
from app.models.user import User, UserSession, UserRole, Role, UserSecurityGroup, SecurityGroup
from app.schemas.schemas import LoginRequest, TokenResponse
from datetime import datetime

router = APIRouter()


def get_user_role(db: Session, user_id: int) -> str:
    ur = db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.is_active == True).first()
    if ur:
        role = db.query(Role).filter(Role.role_id == ur.role_id).first()
        return role.role_name if role else "User"
    return "User"


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email, User.is_active == True).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(data={"sub": str(user.user_id)})
    role = get_user_role(db, user.user_id)

    session = UserSession(user_id=user.user_id, is_active=True)
    db.add(session)
    db.commit()

    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        full_name=f"{user.first_name} {user.last_name}",
        role=role
    )


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(
        UserSession.user_id == current_user.user_id,
        UserSession.is_active == True
    ).order_by(UserSession.login_time.desc()).first()
    if session:
        session.is_active = False
        session.logout_time = datetime.utcnow()
        db.commit()
    return {"message": "Logged out"}


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    current_user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


@router.get("/me")
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = get_user_role(db, current_user.user_id)
    sgs = db.query(SecurityGroup).join(UserSecurityGroup).filter(
        UserSecurityGroup.user_id == current_user.user_id,
        UserSecurityGroup.is_active == True,
        SecurityGroup.is_active == True,
    ).all()
    return {
        "UserID": current_user.user_id,
        "FirstName": current_user.first_name,
        "LastName": current_user.last_name,
        "Email": current_user.email,
        "Contact": current_user.contact,
        "IsActive": current_user.is_active,
        "role": role,
        "security_groups": [{"SecurityGroupID": g.security_group_id, "SecurityGroupName": g.security_group_name} for g in sgs],
    }
