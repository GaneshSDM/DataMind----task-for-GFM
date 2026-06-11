"""
DataFlow Agent — Pydantic request/response models.

These models define the API contract for the Data Workflow microservice (port 8007).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ── Connection Config (inline, one-time) ──────────────────────────────────

class ConnectionConfig(BaseModel):
    """Inline database connection details."""
    model_config = {"protected_namespaces": ()}
    type: str = Field(..., description="Database type: postgresql, mysql, snowflake, bigquery, duckdb, csv")
    connection_string: str = Field(..., description="SQLAlchemy-style connection URL")
    tables: Optional[List[str]] = Field(None, description="Specific tables to operate on")
    schema: Optional[str] = Field(None, description="Target schema name")


# ── Pipeline Configuration ────────────────────────────────────────────────

class PipelineOptions(BaseModel):
    """Optional configuration flags for the data pipeline."""
    pii_mask: bool = Field(False, description="Auto-detect and mask PII columns")
    quality_rules: Optional[List[str]] = Field(None, description="Quality check rules: no_nulls:<col>, unique:<col>, etc.")
    dbt_model: Optional[str] = Field(None, description="dbt model name to run after transforms")
    dbt_project_dir: Optional[str] = Field(None, description="Path to dbt project directory")
    materialization: Optional[str] = Field("table", description="table | view | incremental | ephemeral")
    chunk_size: int = Field(10000, description="Rows per chunk for ingestion")
    dry_run: bool = Field(False, description="Plan only, do not execute")


# ── Workflow Run Request ──────────────────────────────────────────────────

class WorkflowRunRequest(BaseModel):
    """Main request body for /dataflow/run."""
    request_id: str = Field(default_factory=lambda: f"df-{uuid.uuid4().hex[:12]}")
    prompt: str = Field(..., description="Natural language description of the data engineering task")
    source_config: Optional[ConnectionConfig] = Field(None, description="Source database inline config")
    target_config: Optional[ConnectionConfig] = Field(None, description="Target database inline config")
    options: PipelineOptions = Field(default_factory=PipelineOptions)
    security_profile: Optional[dict] = Field(None, description="Security context (domains, RLS, CLS)")
    metadata: dict = Field(default_factory=dict)


# ── Discovery ─────────────────────────────────────────────────────────────

class ColumnProfile(BaseModel):
    name: str
    data_type: str
    nullable: bool
    is_pk: bool = False
    sample_values: List[Any] = []
    distinct_count: Optional[int] = None
    null_count: Optional[int] = None
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    pii_category: Optional[str] = None       # "email" | "phone" | "ssn" | "credit_card" | etc.
    pii_confidence: Optional[float] = None   # 0.0 – 1.0


class TableProfile(BaseModel):
    table_name: str
    row_count: Optional[int] = None
    columns: List[ColumnProfile] = []


class DiscoveryResult(BaseModel):
    tables: List[TableProfile] = []
    warnings: List[str] = []


# ── Ingestion ─────────────────────────────────────────────────────────────

class SchemaMapping(BaseModel):
    source_column: str
    target_column: str
    source_type: str
    target_type: str
    cast_expression: Optional[str] = None


class IngestionResult(BaseModel):
    source_table: str
    target_table: str
    rows_ingested: int
    schema_mappings: List[SchemaMapping] = []
    duration_seconds: float = 0.0
    warnings: List[str] = []


# ── PII Masking ───────────────────────────────────────────────────────────

class MaskedColumn(BaseModel):
    column_name: str
    pii_category: str
    confidence: float
    mask_strategy: str        # SHA256_HASH | NULL | DUMMY | MASK_FIRST_N | MASK_LAST_4 | TOKENIZE
    rows_affected: int = 0


class PIIMaskResult(BaseModel):
    masked_columns: List[MaskedColumn] = []
    total_rows_affected: int = 0
    warnings: List[str] = []


# ── Transformation ────────────────────────────────────────────────────────

class TransformStep(BaseModel):
    name: str
    type: str                    # "sql_template" | "dbt_model"
    input_table: Optional[str] = None
    output_table: str
    materialization: str = "table"
    sql: Optional[str] = None
    dbt_model_name: Optional[str] = None
    rows_affected: int = 0
    duration_seconds: float = 0.0
    log: str = ""


class TransformationResult(BaseModel):
    steps: List[TransformStep] = []
    final_table: Optional[str] = None
    warnings: List[str] = []


# ── Quality ───────────────────────────────────────────────────────────────

class QualityCheck(BaseModel):
    rule: str
    column: Optional[str] = None
    passed: bool
    detail: str
    rows_checked: int = 0
    rows_failed: int = 0


class QualityResult(BaseModel):
    checks: List[QualityCheck] = []
    overall: str                          # "pass" | "warn" | "fail"
    summary: str = ""


# ── Publish / Lineage ─────────────────────────────────────────────────────

class ColumnLineage(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    transform_step: Optional[str] = None


class PublishResult(BaseModel):
    model_config = {"protected_namespaces": ()}
    final_table: str
    schema: str
    row_count: int
    column_lineage: List[ColumnLineage] = []


# ── Workflow Run Response ─────────────────────────────────────────────────

class WorkflowStep(BaseModel):
    step_id: str
    agent: str                       # "discovery" | "ingestion" | "pii_mask" | "transformation" | "quality" | "publish"
    status: str                      # "pending" | "running" | "completed" | "failed" | "skipped"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class WorkflowPlan(BaseModel):
    steps: List[WorkflowStep] = []
    rationale: str = ""              # LLM's explanation of the plan


class WorkflowRunResponse(BaseModel):
    request_id: str
    status: str                      # "planned" | "approved" | "running" | "completed" | "failed"
    plan: Optional[WorkflowPlan] = None
    results: dict = Field(default_factory=dict)   # step_id → result
    final_output: Optional[PublishResult] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ── Discovery / Plan / Preview endpoints ──────────────────────────────────

class DiscoverRequest(BaseModel):
    connection: ConnectionConfig


class PlanRequest(BaseModel):
    prompt: str
    source_config: Optional[ConnectionConfig] = None
    target_config: Optional[ConnectionConfig] = None
    options: PipelineOptions = Field(default_factory=PipelineOptions)
    discovery_result: Optional[DiscoveryResult] = None


class PlanResponse(BaseModel):
    plan: WorkflowPlan
    requires_approval: bool = True