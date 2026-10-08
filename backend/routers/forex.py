"""USD opening cost, actual conversions, explicit cash movements and undo."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from data.data_manager import get_usd_ledgers, get_usd_events, record_usd_event, undo_usd_event

router = APIRouter(prefix='/api/forex', tags=['forex'])


class CashEvent(BaseModel):
    kind: Literal['OPENING', 'EXCHANGE_IN', 'EXCHANGE_OUT', 'DEPOSIT', 'WITHDRAW', 'RECONCILE']
    occurred_at: datetime
    usd_amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    krw_amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    rate: float = Field(default=0, ge=0, allow_inf_nan=False)
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
        raise HTTPException(status_code=410,detail='원가·잔고 정정은 4번 탭의 장부 확인 및 정정에서 사유와 함께 처리해주세요.')
    success, message = record_usd_event(account_id, req.kind, req.occurred_at.isoformat(),
                                       req.usd_amount, req.krw_amount, req.rate, req.notes)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'success': True, 'message': message}


@router.delete('/{account_id}/events/{event_id}')
def cancel_event(account_id: str, event_id: str):
    success, message = undo_usd_event(account_id, event_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'success': True, 'message': message}
