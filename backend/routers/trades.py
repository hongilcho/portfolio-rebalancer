from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import datetime
from data.data_manager import execute_trade, get_trade_history, delete_trade

router = APIRouter(prefix="/api/trades", tags=["trades"])

class TradeBatchItem(BaseModel):
    account_id: str
    asset_id: str
    trade_type: str # 'BUY' or 'SELL'
    quantity: float
    price: float

class BatchTradeRequest(BaseModel):
    trade_date: str # YYYY-MM-DD
    trades: List[TradeBatchItem]

class DeleteTradesRequest(BaseModel):
    trade_ids: List[str]

@router.get("/")
def list_trades(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    asset_id: Optional[str] = Query(None)
):
    trades = get_trade_history()
    
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
        t['total_amount'] = float(t['quantity']) * float(t['price'])
        
    return {"trades": filtered}

@router.post("/batch")
def execute_batch_trades(req: BatchTradeRequest):
    success_count = 0
    errors = []
    
    for item in req.trades:
        if item.quantity <= 0 or item.price <= 0:
            continue
            
        success, msg = execute_trade(
            trade_date=req.trade_date,
            account_id=item.account_id,
            asset_id=item.asset_id,
            trade_type=item.trade_type,
            quantity=item.quantity,
            price=item.price
        )
        if success:
            success_count += 1
        else:
            errors.append(msg)
            
    if errors:
        return {
            "success": success_count > 0,
            "success_count": success_count,
            "errors": errors,
            "message": f"{success_count}건 처리 완료, {len(errors)}건 실패"
        }
        
    return {
        "success": True,
        "success_count": success_count,
        "errors": [],
        "message": f"{success_count}건의 매매 기록이 성공적으로 저장되었습니다."
    }

@router.delete("/batch")
def batch_delete_trades(req: DeleteTradesRequest):
    success_count = 0
    errors = []
    
    for trade_id in req.trade_ids:
        success, msg = delete_trade(trade_id)
        if success:
            success_count += 1
        else:
            errors.append(f"[{trade_id}] {msg}")
            
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
        
    return {
        "success": True,
        "deleted_count": success_count,
        "message": f"{success_count}건의 매매 기록이 성공적으로 삭제 및 복원되었습니다."
    }
