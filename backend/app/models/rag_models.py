import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    Vector = None
    PGVECTOR_AVAILABLE = False

SCHEMA = "tracopp"


# ── RAG_CATEGORY ──────────────────────────────────────────────────────────────
class RagCategory(Base):
    __tablename__ = "rag_category"
    __table_args__ = {'schema': SCHEMA}

    category_id   = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String, nullable=False)
    description   = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_by    = Column(Integer, nullable=False)
    created_date  = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by    = Column(Integer, nullable=True)
    updated_date  = Column(DateTime(timezone=True), nullable=True)

    rag_files = relationship("RagFile", back_populates="category")


# ── RAG_SUB_CATEGORY ──────────────────────────────────────────────────────────
class RagSubCategory(Base):
    __tablename__ = "rag_sub_category"
    __table_args__ = {'schema': SCHEMA}

    sub_category_id   = Column(Integer, primary_key=True, autoincrement=True)
    sub_category_name = Column(String, nullable=False)
    description       = Column(Text, nullable=True)
    is_active         = Column(Boolean, nullable=False, default=True)
    created_by        = Column(Integer, nullable=False)
    created_date      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by        = Column(Integer, nullable=True)
    updated_date      = Column(DateTime(timezone=True), nullable=True)

    rag_files = relationship("RagFile", back_populates="sub_category")


# ── RAG_INGESTION_RUNS ────────────────────────────────────────────────────────
class RagIngestionRun(Base):
    __tablename__ = "rag_ingestion_runs"
    __table_args__ = {'schema': SCHEMA}

    run_id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_name          = Column(String, nullable=True)
    source_type       = Column(String, nullable=False)   # local / gdrive / sharepoint
    started_at        = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at      = Column(DateTime(timezone=True), nullable=True)
    status            = Column(String, nullable=False, default='running')
    # running | completed | completed_with_errors | failed
    total_files_found = Column(Integer, nullable=False, default=0)
    processed_files   = Column(Integer, nullable=False, default=0)
    skipped_files     = Column(Integer, nullable=False, default=0)
    failed_files      = Column(Integer, nullable=False, default=0)
    invalid_files     = Column(Integer, nullable=False, default=0)
    run_summary       = Column(JSONB, nullable=True)
    created_by        = Column(Integer, nullable=False)
    created_date      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by        = Column(Integer, nullable=True)
    updated_date      = Column(DateTime(timezone=True), nullable=True)

    jobs   = relationship("RagIngestionJob",   back_populates="run")
    errors = relationship("RagIngestionError", back_populates="run")


# ── RAG_FILES ─────────────────────────────────────────────────────────────────
class RagFile(Base):
    __tablename__ = "rag_files"
    __table_args__ = {'schema': SCHEMA}

    file_id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_file_name  = Column(String, nullable=False)
    storage_uri         = Column(Text, nullable=False)
    relative_path       = Column(Text, nullable=False)
    file_hash           = Column(String, nullable=False)          # SHA256
    file_type           = Column(String, nullable=False)          # pdf / docx / xlsx / txt / csv
    mime_type           = Column(String, nullable=True)
    file_size_bytes     = Column(BigInteger, nullable=False)
    page_count          = Column(Integer, nullable=True)
    domain_id           = Column(Integer, ForeignKey(f"{SCHEMA}.domain.domain_id"), nullable=False)
    sub_domain_id       = Column(Integer, ForeignKey(f"{SCHEMA}.sub_domain.sub_domain_id"), nullable=False)
    category_id         = Column(Integer, ForeignKey(f"{SCHEMA}.rag_category.category_id"), nullable=False)
    sub_category_id     = Column(Integer, ForeignKey(f"{SCHEMA}.rag_sub_category.sub_category_id"), nullable=True)
    description         = Column(Text, nullable=True)
    subcategory_path    = Column(Text, nullable=True)             # raw nested path e.g. Internal_Audit/FY2026
    version_no          = Column(Integer, nullable=False, default=1)
    status              = Column(String, nullable=False, default='processing')
    # processing | active | archived | failed | missing_from_source | skipped
    # invalid_path_structure | no_text_extracted | unsupported_file_type
    # extractor_not_implemented | deleted
    extraction_method   = Column(String, nullable=True)           # docling / pymupdf / text / csv / placeholder
    embedding_model     = Column(String, nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    file_metadata       = Column(JSONB, nullable=True)
    is_active           = Column(Boolean, nullable=False, default=True)
    created_by          = Column(Integer, nullable=False)
    created_date        = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by          = Column(Integer, nullable=True)
    updated_date        = Column(DateTime(timezone=True), nullable=True)

    domain       = relationship("Domain")
    sub_domain   = relationship("SubDomain")
    category     = relationship("RagCategory",    back_populates="rag_files")
    sub_category = relationship("RagSubCategory", back_populates="rag_files")
    jobs         = relationship("RagIngestionJob",   back_populates="file")
    chunks       = relationship("RagDocumentChunk",  back_populates="file")


# ── RAG_INGESTION_JOBS ────────────────────────────────────────────────────────
class RagIngestionJob(Base):
    __tablename__ = "rag_ingestion_jobs"
    __table_args__ = {'schema': SCHEMA}

    job_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id       = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.rag_ingestion_runs.run_id"), nullable=False)
    file_id      = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.rag_files.file_id"), nullable=True)
    storage_uri  = Column(Text, nullable=False)
    job_type     = Column(String, nullable=False)
    # new_file | replacement | duplicate | missing | invalid_path | unsupported
    status       = Column(String, nullable=False, default='queued')
    # queued | processing | completed | failed | skipped
    message      = Column(Text, nullable=True)
    started_at   = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by   = Column(Integer, nullable=False)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by   = Column(Integer, nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=True)

    run    = relationship("RagIngestionRun", back_populates="jobs")
    file   = relationship("RagFile",         back_populates="jobs")
    errors = relationship("RagIngestionError", back_populates="job")


# ── RAG_INGESTION_ERRORS ──────────────────────────────────────────────────────
class RagIngestionError(Base):
    __tablename__ = "rag_ingestion_errors"
    __table_args__ = {'schema': SCHEMA}

    error_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id        = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.rag_ingestion_runs.run_id"), nullable=False)
    job_id        = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.rag_ingestion_jobs.job_id"), nullable=True)
    file_path     = Column(Text, nullable=False)
    error_type    = Column(String, nullable=False)
    # validation | pdf | db | embedding | extractor | unsupported | duplicate | path_structure
    error_message = Column(Text, nullable=False)
    created_by    = Column(Integer, nullable=False)
    created_date  = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by    = Column(Integer, nullable=True)
    updated_date  = Column(DateTime(timezone=True), nullable=True)

    run = relationship("RagIngestionRun", back_populates="errors")
    job = relationship("RagIngestionJob", back_populates="errors")


# ── RAG_DOCUMENT_CHUNKS ───────────────────────────────────────────────────────
class RagDocumentChunk(Base):
    __tablename__ = "rag_document_chunks"
    __table_args__ = {'schema': SCHEMA}

    chunk_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id        = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.rag_files.file_id"), nullable=False)
    chunk_index    = Column(Integer, nullable=False)              # sequential order within file
    page_number    = Column(Integer, nullable=True)               # source page / sheet / slide
    chunk_text     = Column(Text, nullable=False)
    token_count    = Column(Integer, nullable=True)
    content_type   = Column(String, nullable=True)                # paragraph / table / header / footer / image_ocr
    embedding      = Column(Vector(1024) if Vector else JSONB, nullable=True)
    chunk_metadata = Column(JSONB, nullable=True)
    created_by     = Column(Integer, nullable=False)
    created_date   = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by     = Column(Integer, nullable=True)
    updated_date   = Column(DateTime(timezone=True), nullable=True)

    file = relationship("RagFile", back_populates="chunks")
