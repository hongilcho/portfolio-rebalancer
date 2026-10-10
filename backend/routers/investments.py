"""Authenticated workflow management; no external financial execution."""
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel,Field
from backend.routers.plans import perform
from data.repositories import investments
router=APIRouter(prefix='/api/investments',tags=['investments'])

class Setup(BaseModel):
    request_id:str=Field(min_length=8,max_length=100)
    plan_id:str=Field(min_length=1,max_length=100)
    name:str=Field(default='',max_length=120)
    representative_account_id:str=Field(min_length=1,max_length=100)
    additional_cash_krw:float=Field(default=0,ge=0,le=1e15,allow_inf_nan=False)
    source_limits:dict[str,float]=Field(default_factory=dict,max_length=100)
    usd_krw:float=Field(gt=0,le=1e6,allow_inf_nan=False)
    preview_token:str=Field(default='',pattern=r'^(?:[0-9a-f]{64})?$')
class Link(BaseModel):
    step_id:str=Field(min_length=1,max_length=160)
    revision:int=Field(ge=1)
    record_kind:Literal['TRADE','USD','NOTICE']
    record_id:str=Field(min_length=1,max_length=100)
class State(BaseModel):
    status:Literal['ACTIVE','PAUSED','CLOSED']
    reason:str=Field(default='',max_length=2000)
@router.get('/capabilities')
def capabilities(): return {'investment_protocol':1,'automatic_execution':False}
@router.get('/{pid}')
def read(pid:str): return perform(investments.read,pid)
@router.get('/{pid}/plans')
def start_plans(pid:str): return perform(investments.start_plans,pid)
@router.post('/{pid}/prepare')
def prepare(pid:str,request:Setup): return perform(investments.prepare,pid,request.model_dump(mode='json'))
@router.post('/{pid}')
def create(pid:str,request:Setup): return perform(investments.create,pid,request.model_dump(mode='json'))
@router.get('/{pid}/{cycle_id}')
def details(pid:str,cycle_id:str): return perform(investments.read,pid,cycle_id)
@router.patch('/{pid}/{cycle_id}')
def state(pid:str,cycle_id:str,request:State): return perform(investments.set_status,pid,cycle_id,request.status,request.reason)
@router.get('/{pid}/{cycle_id}/steps/{step_id}/candidates')
def candidates(pid:str,cycle_id:str,step_id:str): return perform(investments.candidates,pid,cycle_id,step_id)
@router.post('/{pid}/{cycle_id}/links')
def link(pid:str,cycle_id:str,request:Link): return perform(investments.link_existing,pid,cycle_id,request.model_dump(mode='json'))
@router.delete('/{pid}/{cycle_id}/links/{result_id}')
def unlink(pid:str,cycle_id:str,result_id:str): return perform(investments.unlink,pid,cycle_id,result_id)

class Goal(BaseModel):
    step_id:str=Field(min_length=1,max_length=160)
    target:float | None=Field(default=None,gt=0,le=1e15,allow_inf_nan=False)
    status:Literal['ACTIVE','EXCLUDED']='ACTIVE'
class Revision(BaseModel):
    request_id:str=Field(min_length=8,max_length=100)
    revision:int=Field(ge=1)
    reason:str=Field(min_length=1,max_length=2000)
    changes:list[Goal]=Field(min_length=1,max_length=100)
@router.patch('/{pid}/{cycle_id}/goals')
def revise(pid:str,cycle_id:str,request:Revision):
    return perform(investments.revise,pid,cycle_id,request.model_dump(mode='json'))
