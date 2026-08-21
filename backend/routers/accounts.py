from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from data.data_manager import (
    get_all_accounts, add_account, update_account, delete_account,
    update_account_settings, update_account_priorities, update_account_limit_exhausted, ACCOUNT_TYPES
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

class ToggleLimitExhaustedRequest(BaseModel):
    is_exhausted: bool

class CreateAccountRequest(BaseModel):
    account_no: str
    account_alias: str
    account_type: str
    deposit_krw: float = 0.0
    deposit_usd: float = 0.0
    annual_limit: float = 0.0
    tax_limit: float = 0.0
    notes: Optional[str] = ""
    priority: int = 99
    limit_preference: str = "ANNUAL"
    current_year_deposit: float = 0.0

class UpdateAccountRequest(BaseModel):
    account_no: str
    account_alias: str
    account_type: str
    deposit_krw: float = 0.0
    deposit_usd: float = 0.0
    annual_limit: float = 0.0
    tax_limit: float = 0.0
    notes: Optional[str] = ""
    priority: int = 99
    limit_preference: str = "ANNUAL"
    current_year_deposit: float = 0.0

class UpdatePrioritiesRequest(BaseModel):
    priority_map: Dict[str, int]

@router.get("/")
def list_accounts():
    accounts = get_all_accounts()
    return {
        "accounts": accounts,
        "account_types": list(ACCOUNT_TYPES.keys())
    }

@router.post("/")
def create_account(req: CreateAccountRequest):
    success, msg = add_account(
        account_no=req.account_no,
        account_alias=req.account_alias,
        account_type=req.account_type,
        deposit_krw=req.deposit_krw,
        deposit_usd=req.deposit_usd,
        annual_limit=req.annual_limit,
        tax_limit=req.tax_limit,
        notes=req.notes or "",
        priority=req.priority,
        limit_preference=req.limit_preference,
        current_year_deposit=req.current_year_deposit
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@router.put("/{account_id}")
def edit_account(account_id: str, req: UpdateAccountRequest):
    success, msg = update_account(
        account_id=account_id,
        account_no=req.account_no,
        account_alias=req.account_alias,
        account_type=req.account_type,
        deposit_krw=req.deposit_krw,
        deposit_usd=req.deposit_usd,
        annual_limit=req.annual_limit,
        tax_limit=req.tax_limit,
        notes=req.notes or "",
        priority=req.priority,
        limit_preference=req.limit_preference,
        current_year_deposit=req.current_year_deposit
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@router.put("/{account_id}/toggle-exhaust")
def toggle_account_limit_exhausted(account_id: str, req: ToggleLimitExhaustedRequest):
    success, msg = update_account_limit_exhausted(account_id, req.is_exhausted)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@router.put("/priorities/batch")
def edit_priorities(req: UpdatePrioritiesRequest):
    success = update_account_priorities(req.priority_map)
    if not success:
        raise HTTPException(status_code=400, detail="우선순위 업데이트에 실패했습니다.")
    return {"success": True, "message": "우선순위가 성공적으로 업데이트되었습니다."}

@router.delete("/{account_id}")
def remove_account(account_id: str):
    success, msg = delete_account(account_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}
