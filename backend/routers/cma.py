"""CMA observation, reviewed income and opt-in policy. Disabled by default."""
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from backend.cma_interest import enabled, poll
from backend.routers.plans import perform
from data.repositories import cma
from logic import cma_policy

router = APIRouter(prefix='/api/cma',tags=['cma'])


def guard(*,write=False):
    if not enabled():
        raise HTTPException(status_code=409,detail='CMA 이자 기능은 운영 검증·승인 전까지 비활성 상태입니다.')
    if write and not cma_policy.writes_enabled():
        raise HTTPException(status_code=409,detail='CMA 장부 쓰기는 별도 운영 승인 전까지 차단되어 있습니다.')


class Commit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=8,max_length=100)
    account_id: str
    observation_id: str
    book_token: str = Field(pattern=r'^[a-f0-9]{64}$')
    interest_krw: Decimal = Field(ge=0,le=Decimal('1e15'),allow_inf_nan=False)
    confirmed_movements: bool


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    auto_apply: bool = False
    max_auto_interest: Decimal = Field(default=0,ge=0,le=Decimal('1e9'),allow_inf_nan=False)
    movements_confirmed: bool = False


class InitialInterest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: str=Field(min_length=8,max_length=100)
    account_id: str
    observation_id: str
    book_token: str=Field(pattern=r'^[a-f0-9]{64}$')
    initial_interest_krw: Decimal=Field(gt=0,le=Decimal('1e15'),allow_inf_nan=False)
    confirmed_initial_interest: bool
    reason: str=Field(min_length=10,max_length=1000)


@router.get('/{pid}')
def read(pid:str):
    if not enabled():
        return dict(enabled=False,accounts=[],income=[],checks=[])
    return dict(enabled=True,writes_enabled=cma_policy.writes_enabled(),automatic_ready=cma_policy.automatic_ready(),**perform(cma.read,pid))


@router.post('/{pid}/{aid}/observe')
def observe(pid:str,aid:str):
    guard()
    return perform(poll,pid,aid)


@router.get('/{pid}/{aid}/preview/{ident}')
def preview(pid:str,aid:str,ident:str):
    guard()
    return perform(cma.preview,pid,aid,ident,datetime.now(timezone.utc))


@router.post('/{pid}/income')
def commit(pid:str,request:Commit):
    guard(write=True)
    return perform(cma.commit,pid,request.model_dump(mode='json'),datetime.now(timezone.utc))


@router.post('/{pid}/{aid}/income/{ident}/undo')
def undo(pid:str,aid:str,ident:str):
    guard(write=True)
    return perform(cma.undo,pid,aid,ident)


@router.put('/{pid}/{aid}/settings')
def configure(pid:str,aid:str,request:Settings):
    guard(write=request.auto_apply)
    return perform(cma.configure,pid,aid,request.model_dump(mode='json'))


@router.post('/{pid}/initial-interest')
def initialize_interest(pid:str,request:InitialInterest):
    guard(write=True)
    return perform(cma.initialize_interest,pid,request.model_dump(mode='json'),datetime.now(timezone.utc))


@router.post('/{pid}/{aid}/initial-interest/{ident}/undo')
def undo_initial_interest(pid:str,aid:str,ident:str):
    guard(write=True)
    return perform(cma.undo_initial_interest,pid,aid,ident)
