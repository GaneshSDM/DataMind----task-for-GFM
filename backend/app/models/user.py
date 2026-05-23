import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

SCHEMA = "tracopp"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {'schema': SCHEMA}
    user_id = Column(Integer, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    contact = Column(String, nullable=True)
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    sessions = relationship("UserSession", back_populates="user")
    user_roles = relationship("UserRole", back_populates="user")
    user_security_groups = relationship("UserSecurityGroup", back_populates="user")


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = {'schema': SCHEMA}
    session_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(f"{SCHEMA}.users.user_id"), nullable=False)
    login_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    logout_time = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="sessions")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {'schema': SCHEMA}
    role_id = Column(Integer, primary_key=True)
    role_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    user_roles = relationship("UserRole", back_populates="role")
    role_permissions = relationship("RolePermission", back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {'schema': SCHEMA}
    permission_id = Column(Integer, primary_key=True)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    role_permissions = relationship("RolePermission", back_populates="permission")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = {'schema': SCHEMA}
    user_id = Column(Integer, ForeignKey(f"{SCHEMA}.users.user_id"), primary_key=True)
    role_id = Column(Integer, ForeignKey(f"{SCHEMA}.roles.role_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = {'schema': SCHEMA}
    role_id = Column(Integer, ForeignKey(f"{SCHEMA}.roles.role_id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey(f"{SCHEMA}.permissions.permission_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class SecurityGroup(Base):
    __tablename__ = "security_group"
    __table_args__ = {'schema': SCHEMA}
    security_group_id = Column(Integer, primary_key=True)
    security_group_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    user_security_groups = relationship("UserSecurityGroup", back_populates="security_group")
    sg_domains = relationship("SecurityGroupDomain", back_populates="security_group")
    sg_subdomains = relationship("SecurityGroupSubDomain", back_populates="security_group")
    sg_geographies = relationship("SecurityGroupGeography", back_populates="security_group")
    sg_rls = relationship("SecurityGroupRLS", back_populates="security_group")
    sg_cls = relationship("SecurityGroupCLS", back_populates="security_group")


class UserSecurityGroup(Base):
    __tablename__ = "user_security_group"
    __table_args__ = {'schema': SCHEMA}
    user_id = Column(Integer, ForeignKey(f"{SCHEMA}.users.user_id"), primary_key=True)
    security_group_id = Column(Integer, ForeignKey(f"{SCHEMA}.security_group.security_group_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="user_security_groups")
    security_group = relationship("SecurityGroup", back_populates="user_security_groups")


class Domain(Base):
    __tablename__ = "domain"
    __table_args__ = {'schema': SCHEMA}
    domain_id = Column(Integer, primary_key=True)
    domain_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    db_schema   = Column(String(100), nullable=True)   # PG schema backing this domain (e.g. 'sales')
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    subdomains = relationship("SubDomain", back_populates="domain")
    sg_domains = relationship("SecurityGroupDomain", back_populates="domain")


class SubDomain(Base):
    __tablename__ = "sub_domain"
    __table_args__ = {'schema': SCHEMA}
    sub_domain_id = Column(Integer, primary_key=True)
    domain_id = Column(Integer, ForeignKey(f"{SCHEMA}.domain.domain_id"), nullable=False)
    sub_domain_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    domain = relationship("Domain", back_populates="subdomains")
    sg_subdomains = relationship("SecurityGroupSubDomain", back_populates="subdomain")


class Geography(Base):
    __tablename__ = "geography"
    __table_args__ = {'schema': SCHEMA}
    geo_id = Column(Integer, primary_key=True)
    geo_name = Column(String, nullable=False)
    geo_type = Column(String, nullable=True)
    parent_geo_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    sg_geographies = relationship("SecurityGroupGeography", back_populates="geography")


class SecurityGroupDomain(Base):
    __tablename__ = "security_group_domain"
    __table_args__ = {'schema': SCHEMA}
    security_group_id = Column(Integer, ForeignKey(f"{SCHEMA}.security_group.security_group_id"), primary_key=True)
    domain_id = Column(Integer, ForeignKey(f"{SCHEMA}.domain.domain_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    security_group = relationship("SecurityGroup", back_populates="sg_domains")
    domain = relationship("Domain", back_populates="sg_domains")


class SecurityGroupSubDomain(Base):
    __tablename__ = "security_group_sub_domain"
    __table_args__ = {'schema': SCHEMA}
    security_group_id = Column(Integer, ForeignKey(f"{SCHEMA}.security_group.security_group_id"), primary_key=True)
    sub_domain_id = Column(Integer, ForeignKey(f"{SCHEMA}.sub_domain.sub_domain_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    security_group = relationship("SecurityGroup", back_populates="sg_subdomains")
    subdomain = relationship("SubDomain", back_populates="sg_subdomains")


class SecurityGroupGeography(Base):
    __tablename__ = "security_group_geography"
    __table_args__ = {'schema': SCHEMA}
    security_group_id = Column(Integer, ForeignKey(f"{SCHEMA}.security_group.security_group_id"), primary_key=True)
    geo_id = Column(Integer, ForeignKey(f"{SCHEMA}.geography.geo_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    security_group = relationship("SecurityGroup", back_populates="sg_geographies")
    geography = relationship("Geography", back_populates="sg_geographies")


class RowLevelSecurity(Base):
    __tablename__ = "row_level_security"
    __table_args__ = {'schema': SCHEMA}
    rls_id = Column(Integer, primary_key=True)
    domain_id = Column(Integer, ForeignKey(f"{SCHEMA}.domain.domain_id"), nullable=False)
    sub_domain_id = Column(Integer, ForeignKey(f"{SCHEMA}.sub_domain.sub_domain_id"), nullable=True)
    rls_name = Column(String, nullable=False)
    target_table = Column(String, nullable=False)
    filter_expression = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now())
    conditions = relationship("RLSCondition", back_populates="rls")
    sg_rls = relationship("SecurityGroupRLS", back_populates="rls")


class RLSCondition(Base):
    __tablename__ = "rls_conditions"
    __table_args__ = {'schema': SCHEMA}
    condition_id = Column(Integer, primary_key=True)
    rls_id = Column(Integer, ForeignKey(f"{SCHEMA}.row_level_security.rls_id"), nullable=False)
    column_name = Column(String, nullable=False)
    operator = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    logical_operator = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False)
    rls = relationship("RowLevelSecurity", back_populates="conditions")


class ColumnLevelSecurity(Base):
    __tablename__ = "column_level_security"
    __table_args__ = {'schema': SCHEMA}
    cls_id = Column(Integer, primary_key=True)
    domain_id = Column(Integer, ForeignKey(f"{SCHEMA}.domain.domain_id"), nullable=False)
    sub_domain_id = Column(Integer, ForeignKey(f"{SCHEMA}.sub_domain.sub_domain_id"), nullable=True)
    cls_name = Column(String, nullable=False)
    target_table = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    column_mappings = relationship("ColumnSecurityMapping", back_populates="cls")
    sg_cls = relationship("SecurityGroupCLS", back_populates="cls")


class ColumnSecurityMapping(Base):
    __tablename__ = "column_security_mapping"
    __table_args__ = {'schema': SCHEMA}
    mapping_id = Column(Integer, primary_key=True)
    cls_id = Column(Integer, ForeignKey(f"{SCHEMA}.column_level_security.cls_id"), nullable=False)
    column_name = Column(String, nullable=False)
    can_read = Column(Boolean, nullable=False)
    can_write = Column(Boolean, nullable=False)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    cls = relationship("ColumnLevelSecurity", back_populates="column_mappings")


class SecurityGroupRLS(Base):
    __tablename__ = "security_group_rls"
    __table_args__ = {'schema': SCHEMA}
    security_group_id = Column(Integer, ForeignKey(f"{SCHEMA}.security_group.security_group_id"), primary_key=True)
    rls_id = Column(Integer, ForeignKey(f"{SCHEMA}.row_level_security.rls_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    security_group = relationship("SecurityGroup", back_populates="sg_rls")
    rls = relationship("RowLevelSecurity", back_populates="sg_rls")


class SecurityGroupCLS(Base):
    __tablename__ = "security_group_cls"
    __table_args__ = {'schema': SCHEMA}
    security_group_id = Column(Integer, ForeignKey(f"{SCHEMA}.security_group.security_group_id"), primary_key=True)
    cls_id = Column(Integer, ForeignKey(f"{SCHEMA}.column_level_security.cls_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    security_group = relationship("SecurityGroup", back_populates="sg_cls")
    cls = relationship("ColumnLevelSecurity", back_populates="sg_cls")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {'schema': SCHEMA}
    audit_id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    ip_address = Column(String, nullable=True)
    status = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)
    action_datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PromptPolicy(Base):
    __tablename__ = "prompt_policies"
    __table_args__ = {'schema': SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    check_type = Column(String, nullable=False)
    guardrail = Column(String, nullable=True, server_default='prompt')
    check_value = Column(JSONB, nullable=False)
    action = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    priority = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=func.now())
    updated_at = Column(DateTime, nullable=True)
    checks = relationship("PromptPolicyCheck", back_populates="policy")


class PromptPolicyCheck(Base):
    __tablename__ = "prompt_policy_checks"
    __table_args__ = {'schema': SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    policy_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.prompt_policies.id"), nullable=True)
    matched = Column(Boolean, nullable=False)
    action_taken = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=func.now())
    prompt = Column(String, nullable=True)
    policy = relationship("PromptPolicy", back_populates="checks")


class ChatHistory(Base):
    __tablename__ = "chat_history"
    __table_args__ = {'schema': SCHEMA}
    chat_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(f"{SCHEMA}.users.user_id"), nullable=False)
    title = Column(String, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_date = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=True)
    messages = relationship("ChatMessage", back_populates="chat")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {'schema': SCHEMA}
    message_id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey(f"{SCHEMA}.chat_history.chat_id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    chat = relationship("ChatHistory", back_populates="messages")


class SLMConfig(Base):
    __tablename__ = "slm_config"
    __table_args__ = {'schema': SCHEMA}
    config_id = Column(Integer, primary_key=True)
    base_url = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    timeout_seconds = Column(Integer, nullable=True)
    max_retries = Column(Integer, nullable=True)
    extra_headers = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=True)


class DBConnection(Base):
    __tablename__ = "db_connections"
    __table_args__ = {'schema': SCHEMA}
    connection_id = Column(Integer, primary_key=True)
    connection_name = Column(String, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=True)
    database_name = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password_encrypted = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_by = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=True)
