"""User-confirmed NH notifications record bookkeeping, never send broker orders."""
from datetime import date, datetime
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel, Field
from backend.routers.plans import perform
from data.repositories import nh_notices

router=APIRouter(prefix='/api/nh-notices',tags=['nh-notices'])


class Cash(BaseModel):
    deposit_krw: float = Field(ge=0,allow_inf_nan=False)
    deposit_usd: float = Field(ge=0,allow_inf_nan=False)


class Row(BaseModel):
    kind: Literal['BUY','DEPOSIT','WITHDRAW','EXCHANGE_IN','KRW_ADJUST']
    account_id: str = Field(min_length=1,max_length=100)
    event_date: date
    occurred_at: datetime | None = None
    source_account_id: str | None = None
    destination_account_id: str | None = None
    cross_portfolio: bool = False
    counterparty_flow_id: str | None = None
    external: bool = True
    apply_cash: bool = True
    existing_flow_id: str | None = None
    duplicate_confirmed: bool = False
    fingerprint: str = Field(default='',pattern=r'^(?:[0-9a-f]{64})?$')
    asset_id: str = ''
    quantity: float = Field(default=0,ge=0,le=1e12,allow_inf_nan=False)
    price: float = Field(default=0,ge=0,le=1e12,allow_inf_nan=False)
    broker_order_no: str = ''
    notes: str = Field(default='',max_length=2000)
    krw_amount: float = Field(default=0,ge=0,le=1e15,allow_inf_nan=False)
    usd_amount: float = Field(default=0,ge=0,le=1e12,allow_inf_nan=False)
    reported_available_krw: float | None = Field(default=None,ge=0,allow_inf_nan=False)
    quoted_rate: float = Field(default=0,ge=0,le=1e6,allow_inf_nan=False)


class Batch(BaseModel):
    request_id: str = Field(min_length=8,max_length=100)
    confirmed: Literal[True]
    rows: list[Row] = Field(min_length=1,max_length=50)
    expected_cash: dict[str,Cash]


@router.get('/{pid}/context')
def context(pid:str,day:date):
    return perform(nh_notices.read_context,pid,day)


@router.post('/{pid}/batch')
def commit(pid:str,req:Batch):
    return perform(nh_notices.commit,pid,req.model_dump(mode='json'))


@router.delete('/{pid}/batch/{batch_id}')
def undo(pid:str,batch_id:str):
    return perform(nh_notices.undo,pid,batch_id)
