"""
매매 기록 및 거래 실행 API 라우터 (Trades Router)
=================================================
리밸런싱 매매 체결 결과의 일괄 기록(Batch Execution),
과거 거래 내역의 다차원 필터링 조회 및 거래 취소(삭제/롤백)를 지원합니다.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from data.data_manager import _context, get_trade_history, delete_trades
from data.repositories import trades as repository

router = APIRouter(prefix="/api/trades", tags=["trades"])

class TradeBatchItem(BaseModel):
    """일괄 체결 개별 거래 아이템 스키마"""
    account_id: str
    asset_id: str
    trade_type: Literal['BUY','SELL']
    quantity: float = Field(gt=0,le=1e12,allow_inf_nan=False)
    price: float = Field(gt=0,le=1e12,allow_inf_nan=False)
    currency: Literal['KRW','USD']
    exchange_rate: Optional[float] = Field(default=None,gt=0,le=1e6,allow_inf_nan=False)
    import_source: Optional[Literal['NAMUH_KAKAO']] = None
    broker_order_no: Optional[str] = None

class BatchTradeRequest(BaseModel):
    """일괄 매매 기록 실행 요청 스키마"""
    request_id: str = Field(min_length=8,max_length=100)
    portfolio_id: str = Field(min_length=1,max_length=100)
    trade_date: str # YYYY-MM-DD
    trades: List[TradeBatchItem] = Field(min_length=1,max_length=100)

class DeleteTradesRequest(BaseModel):
    """매매 기록 일괄 삭제 요청 스키마"""
    trade_ids: List[str]

@router.get('/capabilities')
def capabilities():
    return {'bookkeeping_protocol':1}

@router.get("/")
def list_trades(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    asset_id: Optional[str] = Query(None),
    portfolio_id: Optional[str] = Query(None)
):
    trades = get_trade_history(portfolio_id=portfolio_id)
    
    # Filter in memory
    filtered = trades
    if start_date:
        filtered = [t for t in filtered if str(t['trade_date']) >= start_date]
    if end_date:
        filtered = [t for t in filtered if str(t['trade_date']) <= end_date]
    if account_id and account_id != "all":
        filtered = [t for t in filtered if str(t['account_id']) == account_id]
    if asset_id and asset_id != "all":
        filtered = [t for t in filtered if str(t['asset_id']) == asset_id]
        
    for t in filtered:
        qty = float(t.get('quantity') or 0.0)
        p = float(t.get('price') or 0.0)
        t['total_amount'] = qty * p
        if t.get('currency') == 'USD' or t.get('market') == 'US':
            fx = float(t.get('exchange_rate') or 1.0)
            t['total_amount_krw'] = round(qty * p * fx)
        else:
            t['total_amount_krw'] = round(qty * p)
        
    return {"trades": filtered}

@router.post("/batch")
def execute_batch_trades(req: BatchTradeRequest):
    try:
        return repository.execute_batch(_context(),req.model_dump(mode='json'))
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.delete("/batch")
def batch_delete_trades(req: DeleteTradesRequest):
    success, msg = delete_trades(req.trade_ids)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
        
    return {
        "success": True,
        "deleted_count": len(req.trade_ids),
        "message": msg
    }
