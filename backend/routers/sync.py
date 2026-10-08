"""Broker balances are read-only comparisons, never overwrite app bookkeeping."""
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from data.data_manager import get_all_accounts,get_all_assets,get_all_holdings
from data.nh_api import nh_api_client
router=APIRouter(prefix='/api/sync',tags=['sync'])
class Compare(BaseModel):
    portfolio_id: str
    account_id: str
@router.post('/namuh')
def sync_namuh_accounts():
    raise HTTPException(status_code=410,detail='자동 잔고 덮어쓰기를 중단했습니다. 4번 탭의 나무 잔고 대조를 이용해주세요.')
@router.post('/namuh/compare')
def compare_namuh(req:Compare):
    account=next((a for a in get_all_accounts(portfolio_id=req.portfolio_id) if str(a['id'])==req.account_id),None)
    if not account:raise HTTPException(status_code=404,detail='현재 포트폴리오의 계좌를 선택해주세요.')
    kind=account.get('account_type','')
    if kind in ('ISA','IRP','연금저축계좌','연금','PENSION'):
        raise HTTPException(status_code=400,detail='이 계좌는 현재 나무 API 조회를 지원하지 않습니다. 실제 잔고를 확인해 수동 정정해주세요.')
    if kind=='금현물':data,error=nh_api_client.fetch_gold_account_balance(account['account_no'])
    elif kind=='CMA':data,error=nh_api_client.fetch_account_balance(account['account_no'])
    else:data,error=nh_api_client.fetch_full_account_balance(account['account_no'])
    if not data:raise HTTPException(status_code=502,detail='나무 잔고 조회에 실패했습니다. 현재 장부는 변경하지 않았습니다.')
    holdings=get_all_holdings(portfolio_id=req.portfolio_id)
    assets={str(a['ticker']).upper():a for a in get_all_assets(portfolio_id=req.portfolio_id)}
    comparison=[]
    provided=isinstance(data.get('holdings'),list)
    if provided:
        for h in data['holdings']:
            asset=assets.get(str(h['ticker']).upper());aid=asset['id'] if asset else None
            old=next((v for v in holdings if v['account_id']==req.account_id and v['asset_id']==aid),{})
            comparison.append(dict(asset_id=aid,ticker=h['ticker'],name=asset['name'] if asset else h.get('name',h['ticker']),
                book_quantity=old.get('quantity',0),broker_quantity=h['quantity'],broker_avg_price=h.get('avg_price'),
                broker_avg_price_usd=h.get('avg_price_usd'),market=asset['market'] if asset else None))
        # An omitted ticker may reflect pagination or one market failing. Never infer zero.
    return dict(account_id=req.account_id,book_krw=account['deposit_krw'],book_usd=account.get('deposit_usd',0),
        broker_krw=data.get('deposit_krw'),broker_usd=data.get('deposit_usd'),holdings_provided=provided,holdings=comparison,
        message='조회 결과입니다. 아직 예수금·수량·평단가를 변경하지 않았습니다.')
