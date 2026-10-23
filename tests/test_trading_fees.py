"""Fee rules, real repository paths and audited settlement; synthetic only."""
from datetime import datetime
from uuid import uuid4
import json
import pytest
from logic.trading_fees import estimate,schedule
from logic.realized_gains import calculate
from data.repository_context import RepositoryContext
from data.repositories import trades,forex,ledger_adjustments as repo,nh_notices
from test_trade_reversal import DatabaseAdapter
from test_nh_notices import db,row,payload
from test_ledger_adjustments import book

DAY='2026-01-02'
POLICY={'KR':[{'from':'2026-01-01','rate_pct':'0.0141639'}],
        'US':[{'from':'2026-01-01','rate_pct':'0.07'}],
        'GOLD':[{'from':'2026-01-01','rate_pct':'0.2','vat_included':False}]}

@pytest.mark.parametrize('asset,qty,price,expected',[({'market':'KR'},46,216000,('1407','0')),
    ({'market':'US'},29,100.549,('0','2.04')),({'market':'KR','ticker':'M04020000'},1,1000000,('2200','0'))])
def test_exact_rules_and_original_price_preserved(asset,qty,price,expected):
    result=estimate(POLICY,asset,DAY,qty,price)
    assert (result['krw'],result['usd'])==expected
    assert result['status']=='ESTIMATED' and result['policy']['from']=='2026-01-01'

def test_history_zero_and_missing_are_not_retroactive():
    v={'US':POLICY['US']+[{'from':'2026-02-01','rate_pct':'0'},{'from':'2026-03-01','rate_pct':None}]}
    assert estimate(v,{'market':'US'},'2025-12-31',1,100) is None
    assert estimate(v,{'market':'US'},DAY,1,100)['usd']=='0.07'
    assert estimate(v,{'market':'US'},'2026-02-02',1,100)['usd']=='0.00'
    assert estimate(v,{'market':'US'},'2026-03-02',1,100) is None

@pytest.mark.parametrize('rate',['NaN','Infinity','-1','11','bad'])
def test_invalid_rate_rejected(rate):
    with pytest.raises(ValueError):schedule({'KR':[{'from':DAY,'rate_pct':rate}]})

def fixture_db(policy=POLICY):
    d=DatabaseAdapter();d.raw.execute('UPDATE accounts SET fee_schedule=?',(json.dumps(policy),));d.commit()
    return d,RepositoryContext(lambda:d,lambda:str(uuid4()),lambda:None)

def test_automatic_fees_manual_override_and_original_policy_snapshot():
    d,ctx=fixture_db();ok,msg=trades.execute_trade(ctx,DAY,'acc','ast','BUY',10,10000,'KRW',1)
    assert ok,msg
    t=dict(d.raw.execute('SELECT * FROM trade_history').fetchone());cost=json.loads(t['trade_costs'])
    assert d.raw.execute('SELECT deposit_krw FROM accounts').fetchone()[0]==899986
    assert cost['krw']=='14' and cost['status']=='ESTIMATED'
    assert d.raw.execute('SELECT avg_price FROM holdings').fetchone()[0]==10000
    d.raw.execute("UPDATE accounts SET fee_schedule='{}'");d.commit()
    assert json.loads(d.raw.execute('SELECT trade_costs FROM trade_history').fetchone()[0])==cost
    ok,msg=trades.execute_trade(ctx,'2026-01-03','acc','ast','BUY',1,10000,'KRW',1,fees_krw=0)
    assert ok,msg
    assert d.raw.execute('SELECT deposit_krw FROM accounts').fetchone()[0]==889986
    assert json.loads(d.raw.execute('SELECT trade_costs FROM trade_history ORDER BY trade_sequence DESC').fetchone()[0])['krw']=='0'

def test_estimated_fee_shortage_does_not_block_real_trade_or_make_cash_negative():
    d,ctx=fixture_db();d.raw.execute('UPDATE accounts SET deposit_krw=100000');d.commit()
    ok,msg=trades.execute_trade(ctx,DAY,'acc','ast','BUY',10,10000,'KRW',1);assert ok,msg
    assert d.raw.execute('SELECT deposit_krw FROM accounts').fetchone()[0]==0
    cost=json.loads(d.raw.execute('SELECT trade_costs FROM trade_history').fetchone()[0])
    assert cost['status']=='DEFERRED' and cost['estimated_krw']=='14' and cost['krw']=='0'

def test_managed_usd_fee_cash_and_pool_move_together():
    d,ctx=fixture_db();d.raw.execute("UPDATE assets SET market='US'");d.commit()
    ok,msg=forex.record_cash_event(ctx,'acc','OPENING',DAY+'T00:00:00+09:00',rate=1300);assert ok,msg
    ok,msg=trades.execute_trade(ctx,DAY,'acc','ast','BUY',2,100,'USD',1300);assert ok,msg
    assert d.raw.execute('SELECT deposit_usd FROM accounts').fetchone()[0]==pytest.approx(799.86)
    assert d.raw.execute('SELECT usd_balance FROM usd_cash_state').fetchone()[0]==pytest.approx(799.86)
    event=d.raw.execute("SELECT cash_delta_usd,after_state FROM usd_cash_events WHERE kind='BUY'").fetchone()
    assert event[0]==pytest.approx(-200.14) and float(json.loads(event[1])['usd_balance'])==pytest.approx(799.86)

def test_automatic_estimate_is_not_confirmed_realized_income():
    d,ctx=fixture_db();assert trades.execute_trade(ctx,DAY,'acc','ast','BUY',10,10000,'KRW',1)[0]
    assert trades.execute_trade(ctx,'2026-01-03','acc','ast','SELL',10,11000,'KRW',1)[0]
    ts=[dict(r) for r in d.raw.execute('SELECT * FROM trade_history')]
    result=calculate(ts);assert result['periods'][0]['status']=='CLOSED'
    assert result['sales'][0]['gross_profit_krw']==10000 and result['sales'][0]['net_profit_krw'] is None
    assert result['sales'][0]['estimated_net_profit_krw']==9971

def test_settlement_preserves_positions_history_and_has_idempotent_undo(book):
    before={t:[dict(r) for r in book.raw.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in ('holdings','trade_history','performance_snapshots','performance_flows')}
    preview=repo.settlement_preview(book.ctx,'p','acc','KRW',1999997,'BALANCE_SETTLEMENT','잔돈 차이 확인')
    assert preview['delta']==-3 and preview['history']==[]
    req=dict(proposal=preview['proposal'],token=preview['token'],request_id='fee-settlement-01',decisions={},confirmed=True)
    ident=repo.commit(book.ctx,'p',req)['id'];assert repo.commit(book.ctx,'p',req)['id']==ident
    assert book.balances()[0]==1999997
    for t,rows in before.items():assert [dict(r) for r in book.raw.execute('SELECT * FROM '+t+' ORDER BY 1')]==rows
    assert repo.undo(book.ctx,'p',ident)['reversed'] and book.balances()[0]==2000000

def test_usd_settlement_preserves_average_cost_and_rejects_stale_preview(book):
    preview=repo.settlement_preview(book.ctx,'p','acc','USD',9.97,'COST_SETTLEMENT','비용 차이 확인')
    assert preview['proposal']['usd_average_rate']==1300
    req=dict(proposal=preview['proposal'],token=preview['token'],request_id='fee-settlement-02',decisions={},confirmed=True)
    ident=repo.commit(book.ctx,'p',req)['id']
    state=book.rows('usd_cash_state')[0];assert float(state['usd_balance'])==9.97 and float(state['cost_krw'])==12961
    assert book.balances()[1]==9.97
    assert repo.undo(book.ctx,'p',ident)['reversed'] and book.balances()[1]==10
    preview=repo.settlement_preview(book.ctx,'p','acc','KRW',1999999,'BALANCE_SETTLEMENT','변경 감지 확인')
    req.update(request_id='fee-settlement-03',proposal=preview['proposal'],token=preview['token'])
    book.raw.execute('UPDATE accounts SET deposit_krw=2000001');book.commit()
    with pytest.raises(ValueError,match='변경'):repo.commit(book.ctx,'p',req)


def test_settlement_http_preview_token_survives_request_model_normalization(book,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers import ledger_adjustments as router
    monkeypatch.setattr(router,'perform',lambda fn,*args:fn(book.ctx,*args))
    app=FastAPI();app.include_router(router.router);client=TestClient(app)
    response=client.post('/api/ledger-adjustments/p/settlement-preview',json=dict(account_id='acc',currency='USD',balance=9.97,classification='BALANCE_SETTLEMENT',reason='정기 대조'))
    assert response.status_code==200
    view=response.json();request=dict(request_id='http-settlement-01',proposal=view['proposal'],token=view['token'],decisions={},confirmed=True)
    saved=client.post('/api/ledger-adjustments/p',json=request)
    assert saved.status_code==200 and saved.json()['saved']
    assert client.post('/api/ledger-adjustments/p',json=request).json()==saved.json()
    assert book.balances()[1]==9.97


def test_funding_includes_fee_once_separately_from_price_buffer():
    from logic.investment_execution import build_steps
    policy={'KR':[{'from':'2026-01-01','rate_pct':'1'}]}
    accounts=[dict(id='a',account_alias='합성',account_type='종합매매',deposit_krw=200000,deposit_usd=0,fee_schedule=policy)]
    assets=[dict(id='s',name='합성 ETF',market='KR',allowed_accounts=['a'])]
    plan=dict(trade_plan=[dict(account_id='a',asset_id='s',type='BUY',qty=10,price=10000)])
    setup=dict(representative_account_id='a',usd_krw=1350,price_buffer_percent=1,fx_buffer_percent=0,additional_cash_krw=0)
    funding=build_steps(plan,accounts,assets,setup)[0]['funding']
    assert float(funding['required_krw'])==102000
    assert float(funding['estimated_fee_krw'])==1000 and float(funding['price_buffer_krw'])==1000


def test_rebalance_summary_counts_missing_policies_without_claiming_zero_fee():
    from logic.trading_fees import plan_summary
    accounts=[dict(id='a',fee_schedule=POLICY),dict(id='b')]
    assets=[dict(id='s',market='KR')]
    lines=[dict(account_id=a,asset_id='s',qty=46,price=216000) for a in ('a','b')]
    assert plan_summary(lines,accounts,assets,DAY,1350)==dict(estimated_fee_krw=1407,unconfigured_count=1)
