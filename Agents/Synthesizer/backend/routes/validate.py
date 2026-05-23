"""
POST /api/validate-json
Validates the incoming JSON contract and returns errors / warnings.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from services.json_validator import validate_json_contract

router = APIRouter()


@router.post("/validate-json")
async def validate_json(request: Request):
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "errors": [f"Invalid JSON: {e}"], "warnings": []},
        )

    result = validate_json_contract(payload)
    status_code = 200 if result["valid"] else 422
    return JSONResponse(status_code=status_code, content=result)
