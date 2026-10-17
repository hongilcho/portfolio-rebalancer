"""Synthetic accounting, with no production DB or provider access."""
import json
import pytest
from data import data_manager as dm
from data.repositories import trades
from logic.realized_gains import calculate
from test_trade_reversal import DatabaseAdapter


def trade(i,kind,qty,price,**kw):
    return dict(id=str(i),trade_sequence=i,account_id='acc',asset_id='ast',
                trade_date=f'2026-01-{i:02}',trade_type=kind,quantity=qty,price=price,
                currency='KRW',exchange_rate=1,cash_delta_krw=0,cash_delta_usd=0,
                trade_costs={'krw':'0','usd':'0'},**kw)


def test_partial_full_sale_and_reentry_keep_separate_periods_and_costs():
    rows=[trade(1,'BUY',10,100),trade(2,'BUY',10,200),trade(3,'SELL',5,180),
          trade(4,'SELL',15,140),trade(5,'BUY',2,90)]
    rows[0]['trade_costs']['krw']='20'
    rows[3]['trade_costs']['krw']='10'
    r=calculate(rows)
    assert [s['cost_basis_krw'] for s in r['sales']]==[2250,750]
    assert [s['net_profit_krw'] for s in r['sales']]==[-175,145]
    assert r['summary']['confirmed_net_profit_krw']==-30
    assert [(p['status'],p['start_date'],p['remaining_quantity']) for p in r['periods']]==[
        ('OPEN','2026-01-05',2),('CLOSED','2026-01-01',0)]
    assert r['periods'][1]['end_date']=='2026-01-04'


def test_sale_date_filter_never_filters_earlier_acquisition_basis():
    rows=[trade(1,'BUY',10,100),trade(3,'SELL',4,120),trade(4,'SELL',6,130)]
    r=calculate(rows,start='2026-01-04',end='2026-01-04')
    assert len(r['sales'])==1 and r['sales'][0]['gross_profit_krw']==180
    other={**trade(2,'BUY',10,1),'account_id':'other'}
    assert calculate(rows+[other],account_id='acc')==calculate(rows)


def test_usd_price_and_fx_components_reconcile_to_krw_gross():
    a=trade(1,'BUY',10,100);a.update(currency='USD',exchange_rate=1300)
    b=trade(2,'SELL',4,120);b.update(currency='USD',exchange_rate=1400,trade_costs={'krw':'30','usd':'1'})
    s=calculate([a,b])['sales'][0]
    assert s['price_profit_usd']==80 and s['fx_profit_krw']==40000
    assert s['gross_profit_krw']==80*1400+40000
    assert s['net_profit_krw']==s['gross_profit_krw']-1430


def test_missing_fees_are_unknown_but_explicit_zero_is_confirmed():
    rows=[trade(1,'BUY',10,100),trade(2,'SELL',10,120)]
    rows[0]['trade_costs']=None
    s=calculate(rows)['sales'][0]
    assert s['gross_profit_krw']==200 and s['net_profit_krw'] is None
    assert s['allocated_buy_cost_krw'] is None and s['status']=='COSTS_PENDING'
    rows[0]['trade_costs']={'krw':'0','usd':'0'}
    assert calculate(rows)['sales'][0]['net_profit_krw']==200


def test_legacy_missing_purchase_uses_saved_book_basis_without_inventing_start_date():
    t=trade(2,'SELL',10,120)
    assert calculate([t])['sales'][0]['cost_basis_krw'] is None
    t['accounting_basis']={'source':'BOOK','quantity':'10','avg_krw':'100','avg_usd':'0'}
    r=calculate([t]);s=r['sales'][0]
    assert s['gross_profit_krw']==200 and s['net_profit_krw'] is None
    assert r['periods'][0]['status']=='CLOSED' and r['periods'][0]['start_date'] is None


def test_replay_prefers_corrected_purchase_over_saved_sale_snapshot():
    buy=trade(1,'BUY',10,110);sell=trade(2,'SELL',10,120)
    sell['accounting_basis']={'source':'BOOK','quantity':'10','avg_krw':'100','avg_usd':'0'}
    assert calculate([buy,sell])['sales'][0]['gross_profit_krw']==100
    assert calculate([buy])['sales']==[]  # reversing the sale removes realized income


@pytest.fixture
def db(mocker):
    d=DatabaseAdapter();mocker.patch.object(dm,'get_connection',return_value=d)
    yield d
    d.raw.close()


def record(db,kind,qty,price,fees=0,usd=None,date='2026-01-02'):
    ok,msg=trades.execute_trade(dm._context(),date,'acc','ast',kind,qty,price,
        'USD' if usd is not None else 'KRW',1300,fees_krw=fees,fees_usd=usd)
    assert ok,msg
    return db.raw.execute('SELECT id FROM trade_history ORDER BY trade_sequence DESC LIMIT 1').fetchone()[0]


def test_cash_fees_full_sale_repurchase_and_undo_restore_all(db):
    opening=db.balances()
    buy=record(db,'BUY',10,100,20)
    before=db.state()
    sell=record(db,'SELL',10,120,10,date='2026-01-03')
    assert db.holding()[0]==0 and db.balances()[0]==opening[0]+170
    s=calculate(db.rows('trade_history'))['sales'][0]
    assert s['net_profit_krw']==170
    newbuy=record(db,'BUY',2,200,0,date='2026-01-04')
    assert len(calculate(db.rows('trade_history'))['periods'])==2
    assert dm.delete_trade(newbuy)[0]
    assert dm.delete_trade(sell)[0]
    assert db.state()==before
    assert dm.delete_trade(buy)[0] and db.balances()==opening


def test_fee_failure_rolls_back_principal_holding_history(db):
    before=db.state()
    ok,_=trades.execute_trade(dm._context(),'2026-01-02','acc','ast','BUY',1,100,
        'KRW',1,fees_krw=1_000_000)
    assert not ok and db.state()==before


@pytest.mark.parametrize('kind',['BUY','SELL'])
def test_managed_usd_fee_and_undo_preserve_cash_cost_pool(db,kind):
    db.raw.execute("UPDATE assets SET market='US'");db.commit()
    assert dm.record_usd_event('acc','OPENING','2026-01-01T09:00:00+09:00',rate=1300)[0]
    if kind=='SELL':record(db,'BUY',4,100,0,usd=0)
    pool_state=lambda:dict(db.raw.execute('SELECT * FROM usd_cash_state').fetchone())
    before=db.state(),pool_state()
    tid=record(db,kind,2,120,30,usd=1,date='2026-01-03')
    pool=pool_state()
    assert pool['usd_balance']==db.balances()[1]
    assert dm.delete_trade(tid)[0]
    restored=db.state()
    assert restored['accounts']==before[0]['accounts'] and restored['trade_history']==before[0]['trade_history']
    assert pool_state()==before[1]
    if kind=='SELL':assert restored['holdings']==before[0]['holdings']
    else:assert db.holding()==(0,0,0,0)  # existing reversal retains a harmless zero holding row


def test_batch_receipt_retries_costs_exactly_once(db):
    body=dict(request_id='realized-test-receipt',portfolio_id='p',trade_date='2026-01-02',
        trades=[dict(account_id='acc',asset_id='ast',trade_type='BUY',quantity=2,price=100,
            currency='KRW',exchange_rate=1,fees_krw=10,fees_usd=0)])
    result=trades.execute_batch(dm._context(),body);after=db.state()
    assert trades.execute_batch(dm._context(),body)==result and db.state()==after
    assert db.balances()[0]==999790


def test_confirmation_does_not_change_gross_average_or_portfolio_nav_twice(db):
    record(db,'BUY',10,100,20);record(db,'SELL',5,120,10,date='2026-01-03')
    assert db.holding()[1]==100
    report=calculate(db.rows('trade_history'))
    assert report['sales'][0]['net_profit_krw']==80
    assert db.balances()[0]+db.holding()[0]*120==1_000_170


def test_cached_dividends_remain_with_closed_period_and_manual_override_is_not_duplicated():
    from data.repositories.realized import enrich
    rows=[trade(1,'BUY',10,100),trade(3,'SELL',10,110),trade(3,'BUY',2,120)]
    rows[-1].update(id='rebuy',trade_sequence=4)
    accounts=[dict(id='acc',account_alias='합성 ISA',account_type='ISA')]
    assets=[dict(id='ast',name='합성 ETF',ticker='QA',market='KR')]
    cache={'div_KR_QA':{'data':[dict(date='2026-01-03',amount=5),dict(date='2026-01-04',amount=5)]}}
    r=enrich(rows,[],accounts,assets,cache)
    closed=next(p for p in r['periods'] if p['status']=='CLOSED')
    opened=next(p for p in r['periods'] if p['status']=='OPEN')
    assert closed['dividend_amount']==50 and opened['dividend_amount']==10
    overridden=enrich(rows,[dict(account_id='acc',asset_id='ast',quantity=2,manual_dividend_override=500)],accounts,assets,cache)
    assert all(p['dividend_amount'] is None and p['dividend_source']=='MANUAL_UNALLOCATED' for p in overridden['periods'])


def test_api_validates_dates_and_forwards_scope_without_touching_the_database(mocker):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers.trades import router
    mocked=mocker.patch('data.repositories.realized.read',return_value={'sales':[]})
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/api/trades/realized?portfolio_id=p&start_date=2026-02-01&end_date=2026-01-01').status_code==400
        assert not mocked.called
        assert client.get('/api/trades/realized?portfolio_id=p&account_id=acc&asset_id=ast').json()=={'sales':[]}
    assert mocked.call_args.args[1]=='p' and mocked.call_args.kwargs['account_id']=='acc'


def test_null_fees_from_new_client_can_retry_pre_upgrade_receipt(db):
    body=dict(request_id='pre-upgrade-receipt',portfolio_id='p',trade_date='2026-01-02',
        trades=[dict(account_id='acc',asset_id='ast',trade_type='BUY',quantity=1,price=100,currency='KRW',exchange_rate=1)])
    expected=trades.execute_batch(dm._context(),body);before=db.state()
    body['trades'][0].update(fees_krw=None,fees_usd=None)
    assert trades.execute_batch(dm._context(),body)==expected and db.state()==before


def test_all_unknown_sale_basis_is_never_summarized_as_zero():
    r=calculate([trade(2,'SELL',10,120)])
    assert r['summary']['gross_profit_krw'] is None
    assert r['summary']['confirmed_net_profit_krw'] is None
    assert r['summary']['pending_count']==1
