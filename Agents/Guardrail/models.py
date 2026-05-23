from typing import Optional, List
from pydantic import BaseModel
from typing_extensions import TypedDict


class GuardrailPolicy(BaseModel):
    id: str
    name: str
    type: str


class Guardrails(BaseModel):
    prompt_guardrails: List[GuardrailPolicy] = []
    response_guardrails: List[GuardrailPolicy] = []


class Domain(BaseModel):
    id: int
    name: str


class RLSRule(BaseModel):
    name: str
    table: str
    filter: str


class CLSColumn(BaseModel):
    column: str
    can_read: bool
    can_write: bool


class CLSRule(BaseModel):
    name: str
    table: str
    columns: List[CLSColumn]


class SecurityProfile(BaseModel):
    user_id: str
    role: str
    security_groups: List[str] = []
    domains: List[Domain] = []
    subdomains: List[Domain] = []
    geographies: List[Domain] = []
    row_level_security: List[RLSRule] = []
    column_level_security: List[CLSRule] = []


class Metadata(BaseModel):
    domain: Optional[str] = None
    sub_domain: Optional[str] = None
    geography: Optional[str] = None
    request_id: str


class WatchmanRequest(BaseModel):
    prompt: str
    guardrails: Guardrails
    security_profile: SecurityProfile
    metadata: Metadata


class WatchmanState(TypedDict):
    prompt: str
    guardrails: dict
    security_profile: dict
    metadata: dict
    prompt_embedding: Optional[list]
    status: str
    blocked_by: Optional[str]
    message: str
