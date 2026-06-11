"""
DataFlow proxy routes — proxies /api/dataflow/* to the DataFlow microservice (port 8007).

These routes pass requests through from the frontend (via Vite proxy → backend)
to the dataflow agent. All endpoints require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
import httpx
from app.core.security import get_current_user

router = APIRouter()

DATAFLOW_BASE = "http://localhost:8007"


@router.post("/discover")
async def proxy_discover(req: dict, current_user=Depends(get_current_user)):
    """Proxy POST /dataflow/discover → DataFlow agent."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{DATAFLOW_BASE}/dataflow/discover", json=req)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"DataFlow unavailable: {e}")


@router.post("/upload")
async def proxy_upload(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    """Proxy POST /dataflow/upload → DataFlow agent (multipart file upload)."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            content = await file.read()
            resp = await client.post(
                f"{DATAFLOW_BASE}/dataflow/upload",
                files={"file": (file.filename, content, "text/csv")},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"DataFlow unavailable: {e}")


@router.post("/plan")
async def proxy_plan(req: dict, current_user=Depends(get_current_user)):
    """Proxy POST /dataflow/plan → DataFlow agent."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{DATAFLOW_BASE}/dataflow/plan", json=req)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"DataFlow unavailable: {e}")


@router.post("/run")
async def proxy_run(req: dict, current_user=Depends(get_current_user)):
    """Proxy POST /dataflow/run → DataFlow agent."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            resp = await client.post(f"{DATAFLOW_BASE}/dataflow/run", json=req)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"DataFlow unavailable: {e}")


@router.get("/runs/{request_id}")
async def proxy_get_run(request_id: str, current_user=Depends(get_current_user)):
    """Proxy GET /dataflow/runs/{id} → DataFlow agent."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{DATAFLOW_BASE}/dataflow/runs/{request_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"DataFlow unavailable: {e}")