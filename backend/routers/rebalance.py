from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from backend.services import market_service
from data.data_manager import (
    get_all_assets, get_all_accounts, get_holdings_by_account, apply_transfer_plan
)
from logic.rebalance_calculator import calculate_rebalancing_plan

router = APIRouter(prefix="/api/rebalance", tags=["rebalance"])

class CalculateRebalanceRequest(BaseModel):
    scenario: str = "NEW_CASH" # "NEW_CASH" or "DRIFT"
    new_cash_krw: float = 0.0
    drift_threshold: float = 5.0

class ApplyTransfersRequest(BaseModel):
    transfer_plan: List[Dict[str, Any]]

@router.post("/calculate")
def calculate_plan(req: CalculateRebalanceRequest):
    assets = get_all_assets()
    accounts = get_all_accounts()
    
    if not assets or not accounts:
        raise HTTPException(status_code=400, detail="자산과 계좌를 먼저 등록해주세요.")
        
    prices, price_map = market_service.get_prices()
    
    total_krw_cash = sum(float(a['deposit_krw']) for a in accounts if a['account_type'] != 'CMA')
    
    # Aggregate raw holdings
    holdings_raw = []
    for a in accounts:
        holdings_raw.extend(get_holdings_by_account(a['id']))
        
    portfolio_assets = {}
    for h in holdings_raw:
        aid = str(h['asset_id'])
        qty = float(h['quantity'])
        price = float(price_map.get(aid, 0.0))
        if aid not in portfolio_assets:
            portfolio_assets[aid] = {'qty': 0.0, 'eval_amt_krw': 0.0, 'buy_amt_krw': 0.0}
        portfolio_assets[aid]['qty'] += qty
        portfolio_assets[aid]['eval_amt_krw'] += qty * price
        portfolio_assets[aid]['buy_amt_krw'] += qty * float(h['avg_price'])
        
    t_plan, tr_plan, sim_assets, success, msg = calculate_rebalancing_plan(
        assets=assets,
        portfolio_assets=portfolio_assets,
        accounts=accounts,
        holdings=holdings_raw,
        price_map=price_map,
        total_krw_cash=total_krw_cash,
        usd_krw_rate=market_service.usd_krw,
        scenario=req.scenario,
        new_cash_krw=req.new_cash_krw,
        drift_threshold=req.drift_threshold
    )
    
    if not success:
        return {
            "success": False,
            "message": msg,
            "trade_plan": [],
            "transfer_plan": [],
            "simulated_assets": [],
            "scale_max": 1.0
        }
        
    # Calculate simulation scale_max for visual drift bar
    total_sim = sum(s['projected_val'] for s in sim_assets) if sim_assets else 0.0
    max_drift = 0.0
    for s in sim_assets:
        s['projected_weight'] = (s['projected_val'] / total_sim * 100) if total_sim > 0 else 0.0
        s['drift'] = s['projected_weight'] - float(s['target_weight'])
        if abs(s['drift']) > max_drift:
            max_drift = abs(s['drift'])
            
    scale_max = round(max_drift * 3.5, 1) if max_drift > 0 else 1.0
    
    return {
        "success": True,
        "message": msg,
        "trade_plan": t_plan,
        "transfer_plan": tr_plan,
        "simulated_assets": sim_assets,
        "total_sim": total_sim,
        "scale_max": scale_max
    }

@router.post("/apply-transfers")
def apply_transfers(req: ApplyTransfersRequest):
    success, msg = apply_transfer_plan(req.transfer_plan)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}
