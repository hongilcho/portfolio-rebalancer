"""Bounded, read-only history used by tab 4; no new accounting write paths."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Query
from backend.routers.plans import perform
from data.repositories.activity import read_page
router=APIRouter(prefix='/api/activity',tags=['activity'])
@router.get('/{pid}')
def records(pid:str,start_date:date,end_date:date,account_id:str|None=None,
    category:Literal['TRADE','CASH','USD','ADJUST']|None=None,include_cancelled:bool=False,
    page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),asset_id:str|None=None):
    return perform(read_page,pid,start_date,end_date,account_id,category,include_cancelled,page,page_size,asset_id)
