from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.services import market_service
from data.data_manager import get_all_assets, add_asset, update_asset, delete_asset, toggle_asset_active

router = APIRouter(prefix="/api/assets", tags=["assets"])

class CreateAssetRequest(BaseModel):
    name: str
    ticker: Optional[str] = ""
    market: str = "KR"
    target_weight: float = 0.0
    allowed_accounts: Optional[List[str]] = []
    is_risk_asset: bool = True
    is_active: bool = True
    notes: Optional[str] = ""
    portfolio_id: Optional[str] = "default"
    # Deposit fields
    is_deposit: Optional[bool] = False
    deposit_principal: Optional[float] = 0.0
    interest_rate: Optional[float] = 0.0
    start_date: Optional[str] = ""
    maturity_date: Optional[str] = ""
    early_termination_rate: Optional[float] = 0.0
    tax_rate: Optional[float] = 15.4
    lock_rebalance_sell: Optional[bool] = True
    account_id: Optional[str] = None

class UpdateAssetRequest(BaseModel):
    name: str
    ticker: Optional[str] = ""
    market: str = "KR"
    target_weight: float = 0.0
    allowed_accounts: Optional[List[str]] = []
    is_risk_asset: bool = True
    is_active: bool = True
    notes: Optional[str] = ""
    # Deposit fields
    is_deposit: Optional[bool] = False
    deposit_principal: Optional[float] = 0.0
    interest_rate: Optional[float] = 0.0
    start_date: Optional[str] = ""
    maturity_date: Optional[str] = ""
    early_termination_rate: Optional[float] = 0.0
    tax_rate: Optional[float] = 15.4
    lock_rebalance_sell: Optional[bool] = True
    account_id: Optional[str] = None

class AssetWeightMappingItem(BaseModel):
    id: str
    name: str
    ticker: str
    market: str
    target_weight: float
    allowed_accounts: List[str]
    is_risk_asset: bool
    is_active: Optional[bool] = True
    notes: Optional[str] = ""
    is_deposit: Optional[bool] = False
    deposit_principal: Optional[float] = 0.0
    interest_rate: Optional[float] = 0.0
    start_date: Optional[str] = ""
    maturity_date: Optional[str] = ""
    early_termination_rate: Optional[float] = 0.0
    tax_rate: Optional[float] = 15.4
    lock_rebalance_sell: Optional[bool] = True
    account_id: Optional[str] = None

class BatchWeightsRequest(BaseModel):
    items: List[AssetWeightMappingItem]

class ToggleActiveRequest(BaseModel):
    is_active: bool

@router.get("/")
def list_assets(portfolio_id: Optional[str] = None):
    assets = get_all_assets(portfolio_id=portfolio_id)
    return {"assets": assets}

@router.post("/")
def create_asset(req: CreateAssetRequest):
    success, msg = add_asset(
        name=req.name,
        ticker=req.ticker or "",
        market=req.market,
        target_weight=req.target_weight,
        allowed_accounts=req.allowed_accounts or [],
        is_risk_asset=req.is_risk_asset,
        is_active=req.is_active,
        notes=req.notes or "",
        portfolio_id=req.portfolio_id or "default",
        is_deposit=bool(req.is_deposit),
        deposit_principal=float(req.deposit_principal or 0.0),
        interest_rate=float(req.interest_rate or 0.0),
        start_date=req.start_date or "",
        maturity_date=req.maturity_date or "",
        early_termination_rate=float(req.early_termination_rate or 0.0),
        tax_rate=float(req.tax_rate if req.tax_rate is not None else 15.4),
        lock_rebalance_sell=bool(req.lock_rebalance_sell if req.lock_rebalance_sell is not None else True),
        account_id=req.account_id
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    market_service.invalidate_price_cache()
    return {"success": True, "message": msg}

@router.put("/{asset_id}")
def edit_asset(asset_id: str, req: UpdateAssetRequest):
    success, msg = update_asset(
        asset_id=asset_id,
        name=req.name,
        ticker=req.ticker or "",
        market=req.market,
        target_weight=req.target_weight,
        allowed_accounts=req.allowed_accounts or [],
        is_risk_asset=req.is_risk_asset,
        is_active=req.is_active,
        notes=req.notes or "",
        is_deposit=bool(req.is_deposit),
        deposit_principal=float(req.deposit_principal or 0.0),
        interest_rate=float(req.interest_rate or 0.0),
        start_date=req.start_date or "",
        maturity_date=req.maturity_date or "",
        early_termination_rate=float(req.early_termination_rate or 0.0),
        tax_rate=float(req.tax_rate if req.tax_rate is not None else 15.4),
        lock_rebalance_sell=bool(req.lock_rebalance_sell if req.lock_rebalance_sell is not None else True),
        account_id=req.account_id
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    market_service.invalidate_price_cache()
    return {"success": True, "message": msg}

@router.post("/{asset_id}/active")
@router.patch("/{asset_id}/active")
@router.put("/{asset_id}/active")
def toggle_active(asset_id: str, req: ToggleActiveRequest):
    success, msg = toggle_asset_active(asset_id, req.is_active)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    market_service.invalidate_price_cache()
    return {"success": True, "message": msg}

@router.put("/weights/batch")
def batch_update_weights(req: BatchWeightsRequest):
    errors = []
    for item in req.items:
        success, msg = update_asset(
            asset_id=item.id,
            name=item.name,
            ticker=item.ticker,
            market=item.market,
            target_weight=item.target_weight,
            allowed_accounts=item.allowed_accounts,
            is_risk_asset=item.is_risk_asset,
            is_active=item.is_active if item.is_active is not None else True,
            notes=item.notes or "",
            is_deposit=bool(item.is_deposit),
            deposit_principal=float(item.deposit_principal or 0.0),
            interest_rate=float(item.interest_rate or 0.0),
            start_date=item.start_date or "",
            maturity_date=item.maturity_date or "",
            early_termination_rate=float(item.early_termination_rate or 0.0),
            tax_rate=float(item.tax_rate if item.tax_rate is not None else 15.4),
            lock_rebalance_sell=bool(item.lock_rebalance_sell if item.lock_rebalance_sell is not None else True),
            account_id=item.account_id
        )
        if not success:
            errors.append(f"[{item.name}] {msg}")
            
    market_service.invalidate_price_cache()
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return {"success": True, "message": "목표 비중 및 계좌 매핑이 성공적으로 저장되었습니다."}

@router.delete("/{asset_id}")
def remove_asset(asset_id: str):
    success, msg = delete_asset(asset_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    market_service.invalidate_price_cache()
    return {"success": True, "message": msg}
