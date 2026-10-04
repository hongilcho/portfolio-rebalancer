"""
계좌별 보유 자산 및 잔고 관리 API 라우터 (Holdings Router)
=========================================================
각 계좌에 속한 개별 종목의 보유 수량, 평균 매입단가(KRW),
원화/외화 예수금의 조회 및 저장 기능을 제공합니다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from data.data_manager import (
    get_holdings_by_account, get_all_holdings, save_account_holdings,
    update_account, get_all_accounts, get_all_assets, get_connection
)
from psycopg2.extras import RealDictCursor
from backend.services import market_service
from logic.dividend_fetcher import calculate_adjusted_holding_prices

router = APIRouter(prefix="/api/holdings", tags=["holdings"])

class HoldingInputItem(BaseModel):
    """보유 종목 입력 스키마"""
    asset_id: str
    quantity: float
    avg_price: float = 0.0
    avg_price_usd: Optional[float] = 0.0
    buy_fx_rate: Optional[float] = 0.0
    original_avg_price: Optional[float] = 0.0
    original_avg_price_usd: Optional[float] = 0.0
    first_buy_date: Optional[str] = ""
    manual_dividend_override: Optional[float] = None
    is_dividend_cost_deduct: Optional[bool] = None

class SaveAccountHoldingsRequest(BaseModel):
    """계좌별 예수금 및 보유 종목 저장 요청 스키마"""
    account_id: str
    deposit_krw: float
    deposit_usd: float
    holdings: List[HoldingInputItem]

@router.get("/account/{account_id}")
def get_account_holdings(account_id: str):
    holdings = get_holdings_by_account(account_id)
    usd_krw = market_service.current_snapshot()['usd_krw'] or 1350.0

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT trade_date, trade_type, quantity, asset_id, id
            FROM trade_history
            WHERE account_id = %s
            ORDER BY trade_date ASC, id ASC
        """, (str(account_id),))
        account_trades = cur.fetchall()
    finally:
        conn.close()

    trades_by_asset = {}
    for t in account_trades:
        trades_by_asset.setdefault(str(t['asset_id']), []).append(dict(t))

    for h in holdings:
        aid = str(h['asset_id'])
        h_trades = trades_by_asset.get(aid, [])
        adj = calculate_adjusted_holding_prices(h, h, usd_krw, account_type=h.get('account_type', ''), trades=h_trades)
        h['original_avg_price'] = adj['original_avg_price']
        h['original_avg_price_usd'] = adj['original_avg_price_usd']
        h['adjusted_avg_price'] = adj['avg_price']
        h['adjusted_avg_price_usd'] = adj['avg_price_usd']
        h['cumulative_dividend'] = adj['cumulative_dividend']
        h['total_dividend_profit'] = adj.get('total_dividend_profit', 0.0)
        h['dividend_details'] = adj.get('dividend_details', [])
        h['gross_cumulative_dividend'] = adj['gross_cumulative_dividend']
        h['dividend_tax_rate'] = adj['tax_rate']
        h['dividend_tax_amount'] = adj['tax_amount']
        h['is_tax_deducted'] = adj['is_tax_deducted']
        h['dividend_count'] = adj['dividend_count']
        h['first_buy_date'] = adj['first_buy_date']
        h['is_dividend_cost_deduct'] = adj['is_dividend_cost_deduct']
    return {"holdings": holdings}

@router.get("/all")
def get_all_holdings_list(portfolio_id: Optional[str] = None):
    holdings = get_all_holdings(portfolio_id=portfolio_id)
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
    assets_map = {str(a['id']): a for a in get_all_assets()}
    usd_krw = market_service.current_snapshot()['usd_krw'] or 1350.0

    holdings_data = []
    for item in req.holdings:
        h_dict = item.dict()
        aid = str(h_dict['asset_id'])
        asset_info = assets_map.get(aid, {})
        is_us = (asset_info.get('market') == 'US')
        
        # 미국 자산: 달러 매입단가와 매입환율 상호 연계 보정
        if is_us and h_dict.get('avg_price_usd', 0.0) > 0:
            buy_fx = float(h_dict.get('buy_fx_rate') or 0.0)
            if buy_fx <= 0:
                buy_fx = usd_krw
                h_dict['buy_fx_rate'] = buy_fx
            if h_dict.get('avg_price', 0.0) <= 0:
                h_dict['avg_price'] = round(h_dict['avg_price_usd'] * buy_fx)
        elif is_us and h_dict.get('avg_price', 0.0) > 0 and h_dict.get('avg_price_usd', 0.0) <= 0:
            h_dict['avg_price_usd'] = round(h_dict['avg_price'] / usd_krw, 2)
            if not h_dict.get('buy_fx_rate') or float(h_dict.get('buy_fx_rate')) <= 0:
                h_dict['buy_fx_rate'] = usd_krw

        # 배당차감 자산이거나 original_avg_price가 입력된 경우 상호 보정
        if float(h_dict.get('original_avg_price') or 0.0) > 0 and float(h_dict.get('avg_price') or 0.0) <= 0:
            h_dict['avg_price'] = float(h_dict['original_avg_price'])
        if float(h_dict.get('original_avg_price_usd') or 0.0) > 0 and float(h_dict.get('avg_price_usd') or 0.0) <= 0:
            h_dict['avg_price_usd'] = float(h_dict['original_avg_price_usd'])

        # 최초 매입단가 기본값 보정
        if not h_dict.get('original_avg_price') or float(h_dict['original_avg_price']) <= 0:
            h_dict['original_avg_price'] = h_dict.get('avg_price', 0.0)
        if not h_dict.get('original_avg_price_usd') or float(h_dict['original_avg_price_usd']) <= 0:
            h_dict['original_avg_price_usd'] = h_dict.get('avg_price_usd', 0.0)
            
        holdings_data.append(h_dict)

    if holdings_data:
        success, msg = save_account_holdings(target_acc['id'], holdings_data)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
            
    return {"success": True, "message": "예수금 및 보유 잔고가 성공적으로 저장되었습니다."}

