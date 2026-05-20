from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import UserRole, Role
from app.models.rag_models import (
    RagCategory, RagSubCategory,
    RagIngestionRun, RagIngestionJob, RagIngestionError, RagFile
)
from app.schemas.schemas import (
    RagCategoryCreate, RagCategoryUpdate, RagCategoryOut,
    RagSubCategoryCreate, RagSubCategoryUpdate, RagSubCategoryOut,
    RagRunOut,
    RagFileOut, RagJobOut, RagErrorOut,
    MessageResponse
)
from app.rag.pipeline import process_run

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────
def check_admin(current_user, db):
    ur = db.query(UserRole).filter(
        UserRole.user_id == current_user.user_id,
        UserRole.is_active == True
    ).first()
    if not ur:
        raise HTTPException(status_code=403, detail="Admin only")
    role = db.query(Role).filter(Role.role_id == ur.role_id).first()
    if not role or role.role_name != "Admin":
        raise HTTPException(status_code=403, detail="Admin only")


def uuid_str(val):
    """Safely convert UUID to string for response."""
    return str(val) if val else None


# ── RAG CATEGORY ──────────────────────────────────────────────────────────────
@router.get("/categories", response_model=List[RagCategoryOut])
def list_categories(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(RagCategory).filter(RagCategory.is_active == True).order_by(RagCategory.category_name).all()


@router.post("/categories", response_model=RagCategoryOut)
def create_category(
    payload: RagCategoryCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_admin(current_user, db)
    cat = RagCategory(**payload.model_dump(), is_active=True, created_by=current_user.user_id)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/categories/{category_id}", response_model=RagCategoryOut)
def update_category(
    category_id: int,
    payload: RagCategoryUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_admin(current_user, db)
    cat = db.query(RagCategory).filter(RagCategory.category_id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(cat, field, val)
    cat.updated_by = current_user.user_id
    from sqlalchemy.sql import func
    cat.updated_date = func.now()
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}", response_model=MessageResponse)
def delete_category(
    category_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_admin(current_user, db)
    cat = db.query(RagCategory).filter(RagCategory.category_id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.is_active = False
    cat.updated_by = current_user.user_id
    db.commit()
    return {"message": "Category deactivated"}


# ── RAG SUB-CATEGORY ──────────────────────────────────────────────────────────
@router.get("/sub-categories", response_model=List[RagSubCategoryOut])
def list_sub_categories(
    category_id: int = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    q = db.query(RagSubCategory).filter(RagSubCategory.is_active == True)
    if category_id:
        q = q.filter(RagSubCategory.category_id == category_id)
    return q.order_by(RagSubCategory.sub_category_name).all()


@router.post("/sub-categories", response_model=RagSubCategoryOut)
def create_sub_category(
    payload: RagSubCategoryCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_admin(current_user, db)
    sub = RagSubCategory(**payload.model_dump(), is_active=True, created_by=current_user.user_id)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.put("/sub-categories/{sub_category_id}", response_model=RagSubCategoryOut)
def update_sub_category(
    sub_category_id: int,
    payload: RagSubCategoryUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_admin(current_user, db)
    sub = db.query(RagSubCategory).filter(RagSubCategory.sub_category_id == sub_category_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Sub-category not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(sub, field, val)
    sub.updated_by = current_user.user_id
    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/sub-categories/{sub_category_id}", response_model=MessageResponse)
def delete_sub_category(
    sub_category_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_admin(current_user, db)
    sub = db.query(RagSubCategory).filter(RagSubCategory.sub_category_id == sub_category_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Sub-category not found")
    sub.is_active = False
    sub.updated_by = current_user.user_id
    db.commit()
    return {"message": "Sub-category deactivated"}


# ── RAG INGESTION RUNS ────────────────────────────────────────────────────────
@router.get("/runs", response_model=List[RagRunOut])
def list_runs(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    runs = db.query(RagIngestionRun).order_by(RagIngestionRun.started_at.desc()).limit(100).all()
    return [_run_to_dict(r) for r in runs]


@router.get("/runs/{run_id}", response_model=RagRunOut)
def get_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    run = db.query(RagIngestionRun).filter(RagIngestionRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_dict(run)


@router.post("/runs", response_model=RagRunOut, status_code=202)
async def create_run(
    background_tasks: BackgroundTasks,
    run_name:         str           = Form(...),
    source_type:      str           = Form(...),
    domain_id:        int           = Form(...),
    sub_domain_id:    int           = Form(...),
    category_id:      int           = Form(...),
    sub_category_id:  Optional[int] = Form(None),
    description:      Optional[str] = Form(None),
    files:            List[UploadFile] = File(default=[]),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_admin(current_user, db)

    # Read file bytes now — UploadFile is not safe to use after response is sent
    file_payloads = []
    for uf in files:
        content = await uf.read()
        file_payloads.append({
            'filename':     uf.filename,
            'content':      content,
            'content_type': uf.content_type or '',
            'size':         len(content),
        })

    run = RagIngestionRun(
        run_name          = run_name,
        source_type       = source_type,
        status            = 'pending',
        total_files_found = len(file_payloads),
        created_by        = current_user.user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_id_str = str(run.run_id)
    meta = {
        'domain_id':       domain_id,
        'sub_domain_id':   sub_domain_id,
        'category_id':     category_id,
        'sub_category_id': sub_category_id,
        'description':     description,
        'user_id':         current_user.user_id,
    }

    background_tasks.add_task(process_run, run_id_str, file_payloads, meta)
    return _run_to_dict(run)


def _run_to_dict(r):
    return {
        "run_id":            uuid_str(r.run_id),
        "run_name":          r.run_name,
        "source_type":       r.source_type,
        "started_at":        r.started_at,
        "completed_at":      r.completed_at,
        "status":            r.status,
        "total_files_found": r.total_files_found,
        "processed_files":   r.processed_files,
        "skipped_files":     r.skipped_files,
        "failed_files":      r.failed_files,
        "invalid_files":     r.invalid_files,
        "run_summary":       r.run_summary,
        "created_by":        r.created_by,
        "created_date":      r.created_date,
    }


# ── RAG FILES ─────────────────────────────────────────────────────────────────
@router.get("/files", response_model=List[RagFileOut])
def list_files(
    run_id: str = None,
    domain_id: int = None,
    category_id: int = None,
    status: str = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    q = db.query(RagFile)
    if domain_id:
        q = q.filter(RagFile.domain_id == domain_id)
    if category_id:
        q = q.filter(RagFile.category_id == category_id)
    if status:
        q = q.filter(RagFile.status == status)
    files = q.order_by(RagFile.created_date.desc()).limit(500).all()
    return [_file_to_dict(f) for f in files]


def _file_to_dict(f):
    return {
        "file_id":            uuid_str(f.file_id),
        "original_file_name": f.original_file_name,
        "storage_uri":        f.storage_uri,
        "relative_path":      f.relative_path,
        "file_type":          f.file_type,
        "file_size_bytes":    f.file_size_bytes,
        "page_count":         f.page_count,
        "domain_id":          f.domain_id,
        "sub_domain_id":      f.sub_domain_id,
        "category_id":        f.category_id,
        "sub_category_id":    f.sub_category_id,
        "description":        f.description,
        "subcategory_path":   f.subcategory_path,
        "version_no":         f.version_no,
        "status":             f.status,
        "extraction_method":  f.extraction_method,
        "embedding_model":    f.embedding_model,
        "is_active":          f.is_active,
        "created_date":       f.created_date,
    }


# ── RAG JOBS ──────────────────────────────────────────────────────────────────
@router.get("/runs/{run_id}/jobs", response_model=List[RagJobOut])
def list_jobs(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    jobs = db.query(RagIngestionJob).filter(
        RagIngestionJob.run_id == run_id
    ).order_by(RagIngestionJob.created_date).all()
    return [_job_to_dict(j) for j in jobs]


def _job_to_dict(j):
    return {
        "job_id":       uuid_str(j.job_id),
        "run_id":       uuid_str(j.run_id),
        "file_id":      uuid_str(j.file_id),
        "storage_uri":  j.storage_uri,
        "job_type":     j.job_type,
        "status":       j.status,
        "message":      j.message,
        "started_at":   j.started_at,
        "completed_at": j.completed_at,
        "created_date": j.created_date,
    }


# ── RAG ERRORS ────────────────────────────────────────────────────────────────
@router.get("/runs/{run_id}/errors", response_model=List[RagErrorOut])
def list_errors(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    errors = db.query(RagIngestionError).filter(
        RagIngestionError.run_id == run_id
    ).order_by(RagIngestionError.created_date).all()
    return [_error_to_dict(e) for e in errors]


def _error_to_dict(e):
    return {
        "error_id":      uuid_str(e.error_id),
        "run_id":        uuid_str(e.run_id),
        "job_id":        uuid_str(e.job_id),
        "file_path":     e.file_path,
        "error_type":    e.error_type,
        "error_message": e.error_message,
        "created_date":  e.created_date,
    }
