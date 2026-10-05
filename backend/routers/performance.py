from datetime import date
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.routers.plans import context, perform
from backend.services import market_service
from backend.performance_valuation import current_nav
from data import data_manager as dm
from data.repositories import performance

router=APIRouter(prefix='/api/performance',tags=['performance'])


class Flow(BaseModel):
    request_id: str = Field(min_length=8,max_length=100)
    account_id: str
    event_date: date
    direction: Literal['DEPOSIT','WITHDRAW']
    currency: Literal['KRW','USD'] = 'KRW'
    native_amount: float = Field(gt=0,le=1e15,allow_inf_nan=False)
    exchange_rate: float = Field(default=1,gt=0,le=1e6,allow_inf_nan=False)
    notes: str = Field(default='',max_length=2000)


class Voided(BaseModel):
    voided: bool


class Confirmation(BaseModel):
    revision: int = Field(ge=0)
    through: date
    value: float = Field(ge=0,allow_inf_nan=False)


def capture_current(pid,start=False):
    batch=dm.get_rebalance_batch_data(pid)
    prices,price_map=market_service.get_prices()
    status=market_service.request_status()
    if not status.get('updated_at') or status.get('stale') or status.get('refresh_failed') or status.get('refreshing'):
        if start:
            raise HTTPException(status_code=409,detail='시세·환율이 갱신 중이거나 오래되었습니다. 시세 새로고침 후 기준을 등록해주세요.')
        return {'saved':False,'message':'시세·환율 갱신 대기: 이전 평가액을 덮어쓰지 않았습니다.'}
    fx=market_service.request_snapshot()['usd_krw']
    try:
        value=current_nav(batch,price_map,fx)
        asset_ids={a['id'] for a in batch['assets']}
        payload={'accounts':batch['accounts'],'holdings':batch['holdings'],'assets':batch['assets'],
                 'prices':[p for p in prices if p['id'] in asset_ids],'usd_krw':fx,'market_status':status}
        saved=performance.capture(context(),pid,value,payload,start=start)
        return {'saved':saved,'value_krw':value}
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc


@router.get('/{pid}')
def get_performance(pid:str):
    return perform(performance.read,pid)


@router.post('/{pid}/start')
def start_performance(pid:str):
    return capture_current(pid,start=True)


@router.post('/{pid}/snapshot')
def capture_snapshot(pid:str):
    return capture_current(pid)


@router.post('/{pid}/flows')
def add_flow(pid:str,req:Flow):
    return {'id':perform(performance.add_flow,pid,req.model_dump())}


@router.patch('/{pid}/flows/{ident}')
def void_flow(pid:str,ident:str,req:Voided):
    perform(performance.void_flow,pid,ident,req.voided)
    return {'success':True}


@router.post('/{pid}/confirm')
def confirm_flows(pid:str,req:Confirmation):
    perform(performance.confirm,pid,req.revision,req.through,req.value)
    return {'success':True}
