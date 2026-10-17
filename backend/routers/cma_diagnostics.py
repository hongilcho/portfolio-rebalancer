"""Authenticated, independent NH diagnostic route. No schema or ledger writes."""
import os
from fastapi import APIRouter,HTTPException
from logic.cma_diagnostics import public_diagnostics

router=APIRouter(prefix='/api/cma-diagnostics',tags=['cma-diagnostics'])


def probe(pid,aid,*,accounts=None,provider=None,include_statement=False,collector=None):
    if accounts is None:
        from data.data_manager import get_all_accounts
        accounts=lambda:get_all_accounts(portfolio_id=pid)
    def selected():
        row=next((a for a in accounts() if str(a['id'])==aid),None)
        if not row or row.get('account_type')!='CMA':raise ValueError('현재 포트폴리오의 CMA 계좌를 선택해주세요.')
        return row
    before=selected()
    if include_statement:
        from datetime import datetime,timedelta,timezone
        from data.cma_nh import snapshot,public_snapshot
        if collector is None:
            from data.nh_api import nh_api_client
            collector=lambda number,start,end:snapshot(nh_api_client,number,start,end)
        day=datetime.now(timezone(timedelta(hours=9))).date()
        evidence=collector(before['account_no'],(day-timedelta(days=1)).isoformat(),day.isoformat())
        after=selected()
        return dict(account_id=aid,book_unchanged=before==after,
            statement_diagnostics=public_snapshot(evidence),ledger_write_performed=False)
    if provider is None:
        from data.nh_api import nh_api_client
        provider=nh_api_client.fetch_account_balance
    data,_=provider(before['account_no'])
    if not data or not isinstance(data.get('cma_diagnostics'),dict):
        raise ValueError('진단 항목을 받지 못했습니다. 장부는 변경하지 않았습니다.')
    after=selected()
    return dict(account_id=aid,book_unchanged=before==after,
        diagnostics=public_diagnostics(data['cma_diagnostics']),ledger_write_performed=False)


@router.post('/{pid}/{aid}')
def observe(pid:str,aid:str,include_statement:bool=False):
    if os.getenv('CMA_DIAGNOSTICS_ENABLED','0')!='1':
        raise HTTPException(409,'CMA 읽기 전용 진단은 승인 후 활성화합니다.')
    try:return probe(pid,aid,include_statement=include_statement)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    except Exception:raise HTTPException(502,'CMA 진단을 확인하지 못했습니다. 장부는 변경하지 않았습니다.') from None
