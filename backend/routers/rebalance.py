"""
포트폴리오 리밸런싱 API 라우터 (Rebalance Router)
==================================================
리밸런싱 시뮬레이션 계산 실행 및 산출된 현금 이체 지시서의 실제 계좌 반영을 담당합니다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from backend.services import market_service
from data.data_manager import (
    get_all_assets, get_all_accounts, get_holdings_by_account, apply_transfer_plan
)
from logic.rebalance_calculator import calculate_rebalancing_plan, compute_realized_summary

router = APIRouter(prefix="/api/rebalance", tags=["rebalance"])

class CalculateRebalanceRequest(BaseModel):
    """리밸런싱 계산 요청 스키마"""
    scenario: str = "NEW_CASH"        # 리밸런싱 시나리오 ("NEW_CASH", "DRIFT", "PERIODIC")
    new_cash_krw: float = 0.0         # 신규 투입 현금 (원화)
    drift_threshold: float = 5.0      # 허용 괴리율 (%)
    portfolio_id: Optional[str] = "default" # 대상 포트폴리오 ID

class ApplyTransfersRequest(BaseModel):
    """현금 이체 지시서 반영 요청 스키마"""
    transfer_plan: List[Dict[str, Any]]

@router.post("/calculate")
def calculate_plan(req: CalculateRebalanceRequest):
    """
    지정된 포트폴리오와 시나리오에 따라 최적의 매매 및 계좌 간 현금 이체 계획을 계산합니다.
    """
    pid = req.portfolio_id or "default"
    assets = get_all_assets(portfolio_id=pid)
    accounts = get_all_accounts(portfolio_id=pid)
    
    if not assets or not accounts:
        raise HTTPException(status_code=400, detail="자산과 계좌를 먼저 등록해주세요.")
        
    # 리밸런싱 주문 수량 산출 전 항상 최신 실시간 시장 시세 강제 수집 (1초 소요)
    prices, price_map = market_service.get_prices(force_refresh=True)
    
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

    # Add pure deposit assets to portfolio_assets
    for a in assets:
        if a.get('is_deposit'):
            aid = str(a['id'])
            principal = float(a.get('deposit_principal') or 0.0)
            if principal > 0:
                price = float(price_map.get(aid, principal))
                portfolio_assets[aid] = {
                    'qty': 1.0,
                    'eval_amt_krw': price,
                    'buy_amt_krw': principal
                }
        
    # Filter out inactive assets that have 0 holdings
    active_assets = [
        a for a in assets 
        if a.get('is_active', True) or portfolio_assets.get(str(a['id']), {}).get('qty', 0) > 0
    ]
    
    t_plan, tr_plan, sim_assets, success, msg = calculate_rebalancing_plan(
        assets=active_assets,
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
            "scale_max": 1.0,
            "realized_summary": {
                "has_sell": False,
                "sell_count": 0,
                "total_sell_amount": 0.0,
                "total_cost_basis": 0.0,
                "total_realized_profit": 0.0,
                "total_realized_return_pct": 0.0
            }
        }
        
    # Calculate simulation scale_max for visual drift bar
    total_sim_rebalance = sum(s['projected_val'] for s in sim_assets if s.get('include_in_rebalance', True))
    max_drift = 0.0
    for s in sim_assets:
        if s.get('include_in_rebalance', True):
            s['projected_weight'] = (s['projected_val'] / total_sim_rebalance * 100) if total_sim_rebalance > 0 else 0.0
            s['drift'] = s['projected_weight'] - float(s['target_weight'])
            if abs(s['drift']) > max_drift:
                max_drift = abs(s['drift'])
        else:
            s['projected_weight'] = 0.0
            s['drift'] = 0.0
            
    scale_max = round(max_drift * 3.5, 1) if max_drift > 0 else 1.0
    
    realized_summary = compute_realized_summary(t_plan)
    
    return {
        "success": True,
        "message": msg,
        "trade_plan": t_plan,
        "transfer_plan": tr_plan,
        "simulated_assets": sim_assets,
        "total_sim": total_sim_rebalance,
        "scale_max": scale_max,
        "realized_summary": realized_summary
    }

@router.post("/apply-transfers")
def apply_transfers(req: ApplyTransfersRequest):
    success, msg = apply_transfer_plan(req.transfer_plan)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}
