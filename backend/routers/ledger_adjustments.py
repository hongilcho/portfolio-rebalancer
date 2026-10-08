"""Explicitly confirmed, scoped ledger corrections and historical review."""
from datetime import date
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel,Field,ConfigDict
from backend.routers.plans import perform
from data.repositories import ledger_adjustments
router=APIRouter(prefix='/api/ledger-adjustments',tags=['ledger-adjustments'])
class Proposal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['PAST_WITHDRAWAL','CASH','HOLDING']
    account_id: str=Field(min_length=1,max_length=100)
    event_date: date
    reason: str=Field(min_length=3,max_length=2000)
    currency: Literal['KRW','USD']='KRW'
    amount: float=Field(default=0,ge=0,le=1e15,allow_inf_nan=False)
    balance: float=Field(default=0,ge=0,le=1e15,allow_inf_nan=False)
    usd_average_rate: float=Field(default=0,ge=0,le=1e6,allow_inf_nan=False)
    asset_id: str=''
    quantity: float=Field(default=0,ge=0,le=1e12,allow_inf_nan=False)
    avg_price: float=Field(default=0,ge=0,le=1e12,allow_inf_nan=False)
    avg_price_usd: float=Field(default=0,ge=0,le=1e12,allow_inf_nan=False)
    buy_fx_rate: float=Field(default=0,ge=0,le=1e6,allow_inf_nan=False)
    first_buy_date: date | None=None
    manual_dividend_override: float | None=Field(default=None,ge=0,le=1e15,allow_inf_nan=False)
class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: str=Field(min_length=8,max_length=100)
    token: str=Field(pattern='^[a-f0-9]{64}$')
    decisions: dict[str,Literal['ERROR','NORMAL','UNKNOWN']]=Field(default_factory=dict)
    confirmed: Literal[True]
class Adjustment(Review):
    proposal: Proposal
@router.get('/{pid}')
def read(pid:str):return perform(ledger_adjustments.read,pid)
@router.get('/{pid}/account/{aid}')
def account(pid:str,aid:str):return perform(ledger_adjustments.account,pid,aid)
@router.post('/{pid}/preview')
def preview(pid:str,p:Proposal):return perform(ledger_adjustments.preview,pid,p.model_dump(mode='json'))
@router.post('/{pid}')
def commit(pid:str,r:Adjustment):return perform(ledger_adjustments.commit,pid,r.model_dump(mode='json'))
@router.get('/{pid}/{ident}/review')
def review_preview(pid:str,ident:str):return perform(ledger_adjustments.review_preview,pid,ident)
@router.post('/{pid}/{ident}/review')
def review(pid:str,ident:str,r:Review):return perform(ledger_adjustments.review,pid,ident,r.model_dump(mode='json'))
@router.delete('/{pid}/{ident}')
def undo(pid:str,ident:str):return perform(ledger_adjustments.undo,pid,ident)
