"""Deposit book entries belong to the bookkeeping tab, with reason and receipt."""
from datetime import date, datetime
from data.repositories.forex import KST
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from data.data_manager import _context
from data.repositories import deposits
from backend.services import market_service

router=APIRouter(prefix='/api/deposit-ledger',tags=['deposit-ledger'])


class Contract(BaseModel):
    name: str = Field(min_length=1,max_length=200)
    ticker: str = Field(min_length=1,max_length=100)
    deposit_principal: float = Field(ge=0,le=1e15,allow_inf_nan=False)
    interest_rate: float = Field(ge=0,le=100,allow_inf_nan=False)
    start_date: date
    maturity_date: date
    early_termination_rate: float = Field(default=0,ge=0,le=100,allow_inf_nan=False)
    tax_rate: float = Field(default=15.4,ge=0,le=100,allow_inf_nan=False)
    account_no: str = Field(default='',max_length=100)
    target_weight: float = Field(default=0,ge=0,le=100,allow_inf_nan=False)
    notes: str = Field(default='',max_length=2000)

    @model_validator(mode='after')
    def valid_dates(self):
        if self.start_date>datetime.now(KST).date():raise ValueError('현재 보유한 예금의 실제 가입일을 입력해주세요.')
        if self.maturity_date<=self.start_date:raise ValueError('만기일은 가입일 이후여야 합니다.')
        return self


class Entry(BaseModel):
    request_id: str = Field(min_length=8,max_length=100)
    asset_id: str = Field(min_length=1,max_length=100)
    reason: str = Field(min_length=3,max_length=2000)
    confirmed: bool
    asset: Contract


@router.post('/{pid}')
def save(pid:str,request:Entry):
    if not request.confirmed or len(request.reason.strip())<3:raise HTTPException(400,'정정 사유와 최종 확인이 필요합니다.')
    try:
        result=deposits.save(_context(),pid,request.model_dump(mode='json'))
        market_service.invalidate_price_cache()
        return result
    except ValueError as e:raise HTTPException(400,str(e)) from e


@router.get('/{pid}')
def history(pid:str):
    return {'entries':deposits.history(_context(),pid)}


@router.delete('/{pid}/{asset_id}/{request_id}')
def undo(pid:str,asset_id:str,request_id:str):
    try:
        result=deposits.undo(_context(),pid,asset_id,request_id)
        market_service.invalidate_price_cache()
        return result
    except ValueError as e:raise HTTPException(400,str(e)) from e
