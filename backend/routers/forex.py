"""USD opening cost, actual conversions, explicit cash movements and undo."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from data.data_manager import get_usd_ledgers, get_usd_events, _context, undo_usd_event
from data.repositories import forex as repository
from backend.execution_models import ExecutionLink

router = APIRouter(prefix='/api/forex', tags=['forex'])


class CashEvent(BaseModel):
    execution: ExecutionLink | None = None
    request_id: str | None = Field(default=None,min_length=8,max_length=100)
    portfolio_id: str | None = Field(default=None,min_length=1,max_length=100)
    flow_mode: Literal['EXTERNAL','INCOME','ALREADY_RECORDED'] = 'EXTERNAL'
    existing_flow_id: str | None = None
    duplicate_confirmed: bool = False
    kind: Literal['OPENING', 'EXCHANGE_IN', 'EXCHANGE_OUT', 'DEPOSIT', 'WITHDRAW', 'RECONCILE']
    occurred_at: datetime
    usd_amount: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    krw_amount: float = Field(default=0, ge=0, le=1e15, allow_inf_nan=False)
    rate: float = Field(default=0, ge=0, le=1e6, allow_inf_nan=False)
    notes: str = Field(default='', max_length=2000)


@router.get('/')
def list_ledgers(portfolio_id: str | None = None):
    return {'ledgers': get_usd_ledgers(portfolio_id)}


@router.get('/{account_id}/events')
def list_events(account_id: str):
    return {'events': get_usd_events(account_id)}


@router.post('/{account_id}/events')
def create_event(account_id: str, req: CashEvent):
    if req.kind=='RECONCILE':
        raise HTTPException(status_code=410,detail='원가·잔고 정정은 5번 탭의 장부 확인 및 정정에서 사유와 함께 처리해주세요.')
    if not req.request_id or not req.portfolio_id:
        raise HTTPException(status_code=409,detail='새 장부 입력 방식이 필요합니다. 브라우저를 새로고침한 뒤 5번 탭에서 입력해주세요.')
    try:
        return repository.record_manual_event(_context(),account_id,req.model_dump(mode='json'))
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc


@router.delete('/{account_id}/events/{event_id}')
def cancel_event(account_id: str, event_id: str):
    success, message = undo_usd_event(account_id, event_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'success': True, 'message': message}
