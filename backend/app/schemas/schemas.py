from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any, Dict
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    full_name: str
    role: str


# ── Users ─────────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    FirstName: str
    LastName: str
    Email: str
    Contact: Optional[str] = None
    Password: str
    RoleID: int

class UserUpdate(BaseModel):
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    Contact: Optional[str] = None
    IsActive: Optional[bool] = None
    RoleID: Optional[int] = None

class UserOut(BaseModel):
    UserID: int
    FirstName: str
    LastName: str
    Email: str
    Contact: Optional[str] = None
    IsActive: bool
    CreatedDate: Optional[datetime] = None
    role: Optional[str] = None

    class Config:
        from_attributes = True


# ── Roles ─────────────────────────────────────────────────────────────────────
class RoleOut(BaseModel):
    RoleID: int
    RoleName: str
    Description: Optional[str] = None
    IsActive: bool

    class Config:
        from_attributes = True


# ── Geography ─────────────────────────────────────────────────────────────────
class GeoCreate(BaseModel):
    GeoName: str
    IsActive: Optional[bool] = None

class GeoOut(BaseModel):
    GeoID: int
    GeoName: str
    IsActive: bool
    CreatedDate: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Domain ────────────────────────────────────────────────────────────────────
class DomainCreate(BaseModel):
    DomainName: str
    IsActive: Optional[bool] = None

class DomainOut(BaseModel):
    DomainID: int
    DomainName: str
    IsActive: bool
    CreatedDate: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── SubDomain ─────────────────────────────────────────────────────────────────
class SubDomainCreate(BaseModel):
    DomainID: int
    SubDomainName: str
    IsActive: Optional[bool] = None

class SubDomainOut(BaseModel):
    SubDomainID: int
    DomainID: int
    SubDomainName: str
    IsActive: bool
    domain_name: Optional[str] = None

    class Config:
        from_attributes = True


# ── RLS ───────────────────────────────────────────────────────────────────────
class RLSConditionCreate(BaseModel):
    ColumnName: str
    Operator: str
    Value: str
    LogicalOperator: Optional[str] = "AND"
    SortOrder: Optional[int] = 0

class RLSConditionOut(BaseModel):
    ConditionID: int
    ColumnName: str
    Operator: str
    Value: str
    LogicalOperator: Optional[str]
    SortOrder: int

    class Config:
        from_attributes = True

class RLSCreate(BaseModel):
    RLSName: str
    TargetTable: str
    FilterExpression: Optional[str] = None
    Description: Optional[str] = None
    DomainID: Optional[int] = None
    SubDomainID: Optional[int] = None
    IsActive: Optional[bool] = None
    conditions: Optional[List[RLSConditionCreate]] = []

class RLSOut(BaseModel):
    RLS_ID: int
    RLSName: str
    TargetTable: str
    FilterExpression: Optional[str]
    Description: Optional[str]
    DomainID: Optional[int]
    SubDomainID: Optional[int]
    IsActive: bool
    conditions: List[RLSConditionOut] = []

    class Config:
        from_attributes = True


# ── CLS ───────────────────────────────────────────────────────────────────────
class ColumnMappingCreate(BaseModel):
    ColumnName: str
    CanRead: bool = True
    CanWrite: bool = False

class ColumnMappingOut(BaseModel):
    MappingID: int
    ColumnName: str
    CanRead: bool
    CanWrite: bool
    IsActive: bool

    class Config:
        from_attributes = True

class CLSCreate(BaseModel):
    CLSName: str
    TargetTable: str
    DomainID: Optional[int] = None
    SubDomainID: Optional[int] = None
    IsActive: Optional[bool] = None
    columns: Optional[List[ColumnMappingCreate]] = []

class CLSOut(BaseModel):
    CLS_ID: int
    CLSName: str
    TargetTable: str
    DomainID: Optional[int]
    SubDomainID: Optional[int]
    IsActive: bool
    column_mappings: List[ColumnMappingOut] = []

    class Config:
        from_attributes = True


# ── Security Group ────────────────────────────────────────────────────────────
class SecurityGroupCreate(BaseModel):
    SecurityGroupName: str
    is_active: Optional[bool] = None
    domain_ids: Optional[List[int]] = []
    subdomain_ids: Optional[List[int]] = []
    geo_ids: Optional[List[int]] = []
    rls_ids: Optional[List[int]] = []
    cls_ids: Optional[List[int]] = []

class SecurityGroupOut(BaseModel):
    SecurityGroupID: int
    SecurityGroupName: str
    IsActive: bool
    CreatedDate: Optional[datetime] = None
    domain_ids: List[int] = []
    subdomain_ids: List[int] = []
    geo_ids: List[int] = []
    rls_ids: List[int] = []
    cls_ids: List[int] = []

    class Config:
        from_attributes = True


# ── Guardrails ────────────────────────────────────────────────────────────────
class GuardrailCreate(BaseModel):
    policy_name: str
    description: Optional[str] = None
    check_type: str
    check_value: Dict[str, Any]
    action: str
    severity: str
    priority: int = 100

class GuardrailOut(BaseModel):
    id: int
    policy_name: str
    description: Optional[str]
    check_type: str
    check_value: Dict[str, Any]
    action: str
    severity: str
    priority: int
    is_active: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── SLM Config ────────────────────────────────────────────────────────────────
class SLMConfigCreate(BaseModel):
    BaseURL: str
    APIKey: Optional[str] = None
    TimeoutSeconds: int = 30
    MaxRetries: int = 3
    ExtraHeaders: Optional[Dict[str, str]] = {}

class SLMConfigOut(BaseModel):
    ConfigID: int
    BaseURL: str
    TimeoutSeconds: int
    MaxRetries: int
    ExtraHeaders: Optional[Dict[str, Any]]
    IsActive: bool

    class Config:
        from_attributes = True


# ── DB Connection ─────────────────────────────────────────────────────────────
class DBConnectionCreate(BaseModel):
    ConnectionName: str
    Host: str
    Port: int = 5432
    DatabaseName: str
    Username: str
    Password: Optional[str] = None

class DBConnectionOut(BaseModel):
    ConnectionID: int
    ConnectionName: str
    Host: str
    Port: int
    DatabaseName: str
    Username: str
    IsActive: bool
    CreatedDate: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Chat ──────────────────────────────────────────────────────────────────────
class ChatMessageOut(BaseModel):
    MessageID: int
    Role: str
    Content: str
    Payload: Optional[Any] = None
    CreatedDate: Optional[datetime] = None

    class Config:
        from_attributes = True

class ChatHistoryOut(BaseModel):
    ChatID: int
    Title: Optional[str]
    CreatedDate: Optional[datetime]
    UpdatedDate: Optional[datetime]

    class Config:
        from_attributes = True

class SendPromptRequest(BaseModel):
    chat_id: Optional[int] = None
    prompt: str
    security_group_id: Optional[int] = None
    security_group_ids: Optional[List[int]] = None
    domain: Optional[str] = None
    subdomain: Optional[str] = None
    geography: Optional[str] = None


# ── Generic ───────────────────────────────────────────────────────────────────
class MessageResponse(BaseModel):
    message: str

class StatusResponse(BaseModel):
    status: str
    detail: Optional[str] = None
