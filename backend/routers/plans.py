"""Plan recording never executes trades or changes account cash."""
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from data import data_manager as dm
from data.repository_context import RepositoryContext
from data.repositories import plans

router = APIRouter(prefix='/api/plans', tags=['plans'])


def context():
    return RepositoryContext(dm.get_connection, dm.generate_id, dm.clear_all_caches)


def perform(fn, *args):
    try:
        return fn(context(), *args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class Line(BaseModel):
    account_id: str
    asset_id: str
    account_alias: str = ''
    asset_name: str = ''
    type: Literal['BUY','SELL']
    qty: float = Field(gt=0,allow_inf_nan=False)
    price: float = Field(ge=0,allow_inf_nan=False)
    total_krw: float = Field(ge=0,allow_inf_nan=False)


class Plan(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    scenario: Literal['NEW_CASH','DRIFT','PERIODIC']
    new_cash_krw: float = Field(ge=0,allow_inf_nan=False)
    drift_threshold: float = Field(ge=0,allow_inf_nan=False)
    trade_plan: list[Line] = Field(min_length=1,max_length=500)
    transfer_plan: list[dict] = Field(default_factory=list,max_length=500)


class Link(BaseModel):
    line_no: int = Field(ge=0)
    trade_id: str


class Archive(BaseModel):
    archived: bool


@router.get('/{pid}')
def list_plans(pid: str):
    return perform(plans.read, pid)


@router.post('/{pid}')
def save_plan(pid: str, req: Plan):
    return {'id':perform(plans.save,pid,req.name,req.model_dump())}


@router.post('/{pid}/{plan_id}/links')
def add_link(pid: str, plan_id: str, req: Link):
    perform(plans.link,pid,plan_id,req.line_no,req.trade_id)
    return {'success':True}


@router.delete('/{pid}/{plan_id}/links/{trade_id}')
def remove_link(pid: str, plan_id: str, trade_id: str):
    perform(plans.unlink,pid,plan_id,trade_id)
    return {'success':True}


@router.patch('/{pid}/{plan_id}')
def archive_plan(pid: str, plan_id: str, req: Archive):
    perform(plans.archive,pid,plan_id,req.archived)
    return {'success':True}


@router.delete('/{pid}/{plan_id}')
def delete_plan(pid: str,plan_id: str):
    perform(plans.delete,pid,plan_id)
    return {'success':True}
