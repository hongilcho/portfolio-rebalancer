"""Legacy INIT overlap and analysis-only carry-forward, using synthetic accounts."""
from datetime import datetime
from copy import deepcopy
import pytest
from data import data_manager as dm
from data.repositories import realized_openings as repo
from logic import realized_opening as policy
from logic.realized_gains import calculate
from test_trade_reversal import DatabaseAdapter,CursorAdapter
from test_realized_gains import trade

NOW=datetime.fromisoformat('2026-10-10T12:00:00+09:00')


class Cursor(CursorAdapter):
    def execute(self,sql,params=()):
        if sql.startswith('SET TRANSACTION'):return None
        return super().execute(sql,params)


class Database(DatabaseAdapter):
    def cursor(self,**kwargs):return Cursor(self)


@pytest.fixture
def db(mocker):
    d=Database();mocker.patch.object(dm,'get_connection',return_value=d)
    yield d
    d.raw.close()


def legacy(db,qty=9,overlap=5,currency='KRW'):
    db.raw.execute('UPDATE assets SET market=?',('US' if currency=='USD' else 'KR',));db.commit()
    assert dm.execute_trade('2026-09-28','acc','ast','INIT',qty,100,currency,1300)[0]
    assert dm.execute_trade('2026-09-29','acc','ast','BUY',overlap,100,currency,1300)[0]
    db.raw.execute('UPDATE holdings SET quantity=?',(qty,));db.commit()


def request(db,rid='opening-confirmed'):
    rows=repo.preview(dm._context(),'p')['candidates'];assert len(rows)==1
    return dict(request_id=rid,positions=[{k:rows[0][k] for k in ('account_id','asset_id','book_token')}])


def openings(db):
    c=db.cursor();return repo.load(c,'p')


def report(db):return calculate(db.rows('trade_history'),db.rows('holdings'),baselines=openings(db))


@pytest.mark.parametrize('qty,overlap',[(70,40),(9,5),(63,52)])
def test_overlap_is_resolved_without_touching_existing_financial_data(db,qty,overlap):
    legacy(db,qty,overlap);before=deepcopy(db.state())
    assert calculate(db.rows('trade_history'),db.rows('holdings'))['warnings']
    result=repo.commit(dm._context(),'p',request(db),NOW)
    r=report(db)
    assert db.state()==before
    assert not r['warnings'] and r['periods'][0]['remaining_quantity']==qty
    assert r['periods'][0]['start_date'] is None and r['periods'][0]['calculation_start_date']=='2026-10-10'
    assert r['sales']==[] and result['holdings_changed'] is False
    assert repo.preview(dm._context(),'p')['candidates']==[]


def test_future_buy_partial_full_sale_and_reentry_use_fixed_book_cost(db):
    legacy(db);repo.commit(dm._context(),'p',request(db),NOW)
    def add(kind,qty,price,day):
        ok,msg=dm.execute_trade(day,'acc','ast',kind,qty,price,'KRW',1);assert ok,msg
        return db.raw.execute('SELECT id FROM trade_history ORDER BY trade_sequence DESC LIMIT 1').fetchone()[0]
    add('BUY',1,200,'2026-10-11')
    first=add('SELL',4,150,'2026-10-12')
    last=add('SELL',6,120,'2026-10-13')
    r=report(db)
    assert not r['warnings'] and r['summary']['gross_profit_krw']==220
    assert r['summary']['confirmed_net_profit_krw'] is None  # old acquisition fees remain unknown
    assert r['periods'][0]['status']=='CLOSED'
    new=add('BUY',2,90,'2026-10-14')
    assert len(report(db)['periods'])==2
    assert dm.delete_trade(new)[0] and dm.delete_trade(last)[0] and dm.delete_trade(first)[0]
    assert not report(db)['warnings'] and report(db)['sales']==[]
    assert report(db)['periods'][0]['remaining_quantity']==10


def test_exact_retry_survives_later_trade_and_duplicate_capture_does_not(db):
    legacy(db);body=request(db);result=repo.commit(dm._context(),'p',body,NOW)
    assert dm.execute_trade('2026-10-11','acc','ast','BUY',1,100,'KRW',1)[0]
    before=db.state()
    assert repo.commit(dm._context(),'p',body,NOW)==result and db.state()==before
    with pytest.raises(ValueError,match='이미 확정'):
        repo.commit(dm._context(),'p',{**body,'request_id':'different-request'},NOW)
    assert len(openings(db))==1


def test_stale_preview_and_wrong_portfolio_roll_back_receipt(db):
    legacy(db);body=request(db)
    assert dm.execute_trade('2026-10-11','acc','ast','BUY',1,100,'KRW',1)[0]
    before=db.state()
    with pytest.raises(ValueError,match='장부가 변경'):repo.commit(dm._context(),'p',body,NOW)
    assert not openings(db) and db.state()==before
    assert db.raw.execute("SELECT count(*) FROM bookkeeping_requests WHERE scope='realized-opening:p'").fetchone()[0]==0
    with pytest.raises(ValueError,match='포트폴리오'):repo.commit(dm._context(),'other',request(db,'other-scope'),NOW)


def test_revoke_is_a_new_audit_record_and_never_edits_the_book(db):
    legacy(db);result=repo.commit(dm._context(),'p',request(db),NOW);before=db.state()
    body=dict(request_id='revoke-opening-request',baseline_id=result['positions'][0]['id'])
    undone=repo.revoke(dm._context(),'p',body)
    assert repo.revoke(dm._context(),'p',body)==undone
    assert db.state()==before and not openings(db)
    assert db.raw.execute("SELECT count(*) FROM bookkeeping_requests WHERE scope='realized-opening:p'").fetchone()[0]==2
    assert report(db)['warnings']


def test_used_sale_basis_cannot_be_revoked_but_does_not_block_new_trades(db):
    legacy(db);saved=repo.commit(dm._context(),'p',request(db),NOW)
    assert dm.execute_trade('2026-10-11','acc','ast','SELL',1,120,'KRW',1)[0]
    before=db.state()
    with pytest.raises(ValueError,match='매도 손익'):
        repo.revoke(dm._context(),'p',dict(request_id='used-baseline-undo',baseline_id=saved['positions'][0]['id']))
    assert db.state()==before
    assert dm.execute_trade('2026-10-12','acc','ast','BUY',1,100,'KRW',1)[0]
    assert not report(db)['warnings']


def test_changed_covered_history_and_backdated_additions_are_not_silently_accepted():
    rows=[trade(1,'INIT',9,100),trade(2,'BUY',5,100)]
    holding=dict(account_id='acc',asset_id='ast',quantity=9,avg_price=100)
    b=policy.create('p',holding,rows,'request-id',NOW)
    changed=deepcopy(rows);changed[0]['quantity']=8
    sale=trade(20,'SELL',1,120)
    assert policy.validity(b,changed)
    assert calculate(changed+[sale],baselines=[b])['sales'][0]['cost_basis_krw'] is None
    assert policy.validity(b,rows+[trade(3,'BUY',1,100)])


def test_opening_preserves_managed_dollar_cash_and_its_existing_audit(db):
    legacy(db,5,2,'USD')
    assert dm.record_usd_event('acc','OPENING','2026-10-01T12:00:00+09:00',rate=1300)[0]
    before=db.state(),db.rows('usd_cash_events'),list(db.raw.execute('SELECT * FROM usd_cash_state'))
    repo.commit(dm._context(),'p',request(db),NOW)
    assert (db.state(),db.rows('usd_cash_events'),list(db.raw.execute('SELECT * FROM usd_cash_state')))==before
    assert dm.execute_trade('2026-10-11','acc','ast','SELL',1,120,'USD',1400)[0]
    r=report(db);assert not r['warnings'] and r['sales'][0]['gross_profit_krw']==38000


def test_old_realized_sales_are_never_folded_into_a_new_opening(db):
    legacy(db);assert dm.execute_trade('2026-10-01','acc','ast','SELL',1,120,'KRW',1)[0]
    h=db.rows('holdings')[0];rows=db.rows('trade_history')
    with pytest.raises(ValueError,match='기존 매도'):policy.create('p',h,rows,'old-sale',NOW)


def test_covered_trade_delete_never_rewrites_confirmed_book(db):
    legacy(db);repo.commit(dm._context(),'p',request(db),NOW);before=db.state()
    tid=db.rows('trade_history')[0]['id']
    ok,msg=dm.delete_trade(tid)
    assert not ok and '보존 중인 과거 기록' in msg and db.state()==before


def test_same_day_and_backdated_post_opening_trades_use_book_seed(db):
    legacy(db);repo.commit(dm._context(),'p',request(db),NOW)
    assert dm.execute_trade('2026-10-12','acc','ast','BUY',1,200,'KRW',1)[0]
    ok,msg=dm.execute_trade('2026-10-11','acc','ast','SELL',2,120,'KRW',1)
    assert ok,msg
    assert db.holding()[0]==8 and not report(db)['warnings']
    assert report(db)['sales'][0]['gross_profit_krw']==40


def test_opening_dividends_exclude_old_overlap_and_keep_original_override():
    from data.repositories.realized import enrich
    rows=[trade(1,'INIT',9,100),trade(2,'BUY',5,100)]
    h=dict(account_id='acc',asset_id='ast',quantity=9,avg_price=100)
    b=policy.create('p',h,rows,'request-id',NOW)
    accounts=[dict(id='acc',account_alias='QA',account_type='ISA')]
    assets=[dict(id='ast',name='QA ETF',ticker='QA',market='KR')]
    cache={'div_KR_QA':{'data':[dict(date='2026-01-03',amount=5),dict(date='2026-10-11',amount=5)]}}
    r=enrich(rows,[h],accounts,assets,cache,baselines=[b])
    assert r['periods'][0]['dividend_amount']==45
    r=enrich(rows,[{**h,'manual_dividend_override':500}],accounts,assets,cache,baselines=[b])
    assert r['periods'][0]['dividend_source']=='MANUAL_UNALLOCATED' and r['periods'][0]['dividend_amount'] is None
