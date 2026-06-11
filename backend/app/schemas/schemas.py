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


# ── Agent Config ──────────────────────────────────────────────────────────────
class AgentConfigUpdate(BaseModel):
    config: Dict[str, Any]

class AgentConfigResponse(BaseModel):
    agent_id:     int
    agent_name:   str
    display_name: str
    description:  Optional[str] = None
    port:         Optional[int] = None
    config:       Dict[str, Any]
    is_active:    bool
    updated_date: Optional[datetime] = None
    updated_by:   Optional[int] = None

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
    DbSchema:   Optional[str] = None   # PG schema name, e.g. 'sales'
    IsActive:   Optional[bool] = None

class DomainOut(BaseModel):
    DomainID:    int
    DomainName:  str
    DbSchema:    Optional[str] = None
    IsActive:    bool
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
    guardrail: str = 'prompt'
    check_value: Optional[Dict[str, Any]] = None
    action: str
    severity: str
    priority: Optional[int] = 100

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
    DbType: str = "postgres"          # 'postgres' | 'snowflake'
    Host: str
    Port: int = 5432
    DatabaseName: str
    Username: str
    Password: Optional[str] = None
    # Snowflake-specific fields (ignored for postgres)
    Account: Optional[str] = None
    Warehouse: Optional[str] = None
    Role: Optional[str] = None
    Schema: Optional[str] = None
    Authenticator: Optional[str] = None  # 'externalbrowser' | 'snowflake' | 'oauth'

class DBConnectionOut(BaseModel):
    ConnectionID: int
    ConnectionName: str
    DbType: str
    Host: str
    Port: Optional[int] = None
    DatabaseName: str
    Username: str
    Warehouse: Optional[str] = None
    Role: Optional[str] = None
    Schema: Optional[str] = None
    Authenticator: Optional[str] = None
    Account: Optional[str] = None
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


# ── RAG Category ──────────────────────────────────────────────────────────────
class RagCategoryCreate(BaseModel):
    category_name: str
    description:   Optional[str] = None

class RagCategoryUpdate(BaseModel):
    category_name: Optional[str] = None
    description:   Optional[str] = None
    is_active:     Optional[bool] = None

class RagCategoryOut(BaseModel):
    category_id:   int
    category_name: str
    description:   Optional[str]
    is_active:     bool
    created_by:    int
    created_date:  Optional[datetime]

    class Config:
        from_attributes = True


# ── RAG Sub-Category ──────────────────────────────────────────────────────────
class RagSubCategoryCreate(BaseModel):
    sub_category_name: str
    description:       Optional[str] = None

class RagSubCategoryUpdate(BaseModel):
    sub_category_name: Optional[str] = None
    description:       Optional[str] = None
    is_active:         Optional[bool] = None

class RagSubCategoryOut(BaseModel):
    sub_category_id:   int
    sub_category_name: str
    description:       Optional[str]
    is_active:         bool
    created_by:        int
    created_date:      Optional[datetime]

    class Config:
        from_attributes = True


# ── RAG Ingestion Runs ────────────────────────────────────────────────────────
class RagRunCreate(BaseModel):
    run_name:    Optional[str] = None
    source_type: str                      # local / gdrive / sharepoint
    # file metadata submitted by frontend for job record creation
    files: Optional[List[Dict[str, Any]]] = []

class RagRunOut(BaseModel):
    run_id:            str
    run_name:          Optional[str]
    source_type:       str
    started_at:        Optional[datetime]
    completed_at:      Optional[datetime]
    status:            str
    total_files_found: int
    processed_files:   int
    skipped_files:     int
    failed_files:      int
    invalid_files:     int
    run_summary:       Optional[Dict[str, Any]]
    created_by:        int
    created_date:      Optional[datetime]

    class Config:
        from_attributes = True


# ── RAG Files ─────────────────────────────────────────────────────────────────
class RagFileOut(BaseModel):
    file_id:            str
    original_file_name: str
    storage_uri:        str
    relative_path:      str
    file_type:          str
    file_size_bytes:    int
    page_count:         Optional[int]
    domain_id:          int
    sub_domain_id:      int
    category_id:        int
    sub_category_id:    Optional[int]
    description:        Optional[str]
    subcategory_path:   Optional[str]
    version_no:         int
    status:             str
    extraction_method:  Optional[str]
    embedding_model:    Optional[str]
    is_active:          bool
    created_date:       Optional[datetime]

    class Config:
        from_attributes = True


# ── RAG Ingestion Jobs ────────────────────────────────────────────────────────
class RagJobOut(BaseModel):
    job_id:       str
    run_id:       str
    file_id:      Optional[str]
    storage_uri:  str
    job_type:     str
    status:       str
    message:      Optional[str]
    started_at:   Optional[datetime]
    completed_at: Optional[datetime]
    created_date: Optional[datetime]

    class Config:
        from_attributes = True


# ── RAG Ingestion Errors ──────────────────────────────────────────────────────
class RagErrorOut(BaseModel):
    error_id:      str
    run_id:        str
    job_id:        Optional[str]
    file_path:     str
    error_type:    str
    error_message: str
    created_date:  Optional[datetime]

    class Config:
        from_attributes = True
