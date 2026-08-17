from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from data.data_manager import (
    get_holdings_by_account, get_all_holdings, save_account_holdings,
    update_account, get_all_accounts
)

router = APIRouter(prefix="/api/holdings", tags=["holdings"])

class HoldingInputItem(BaseModel):
    asset_id: str
    quantity: float
    avg_price: float

class SaveAccountHoldingsRequest(BaseModel):
    account_id: str
    deposit_krw: float
    deposit_usd: float
    holdings: List[HoldingInputItem]

@router.get("/account/{account_id}")
def get_account_holdings(account_id: str):
    holdings = get_holdings_by_account(account_id)
    return {"holdings": holdings}

@router.get("/all")
def get_all_holdings_list():
    holdings = get_all_holdings()
    return {"holdings": holdings}

@router.post("/save")
def save_holdings(req: SaveAccountHoldingsRequest):
    accounts = get_all_accounts()
    target_acc = next((a for a in accounts if str(a['id']) == str(req.account_id)), None)
    if not target_acc:
        raise HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다.")
        
    # 1. Update deposit
    update_account(
        account_id=target_acc['id'],
        account_no=target_acc['account_no'],
        account_alias=target_acc['account_alias'],
        account_type=target_acc['account_type'],
        deposit_krw=req.deposit_krw,
        deposit_usd=req.deposit_usd,
        annual_limit=float(target_acc.get('annual_limit', 0.0)),
        tax_limit=float(target_acc.get('tax_limit', 0.0)),
        notes=target_acc.get('notes', ''),
        priority=int(target_acc.get('priority', 99)),
        limit_preference=target_acc.get('limit_preference', 'ANNUAL'),
        current_year_deposit=float(target_acc.get('current_year_deposit', 0.0))
    )
    
    # 2. Save holdings
    holdings_data = [item.dict() for item in req.holdings]
    if holdings_data:
        success, msg = save_account_holdings(target_acc['id'], holdings_data)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
            
    return {"success": True, "message": "예수금 및 보유 잔고가 성공적으로 저장되었습니다."}
