"""One-time admin path; no app registration UI/API and no production access."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from data import data_manager as dm
from data.repositories import realized_openings as repo
from logic.realized_gains import calculate
from scripts import repair_realized_openings_once as repair
from test_realized_opening import Database


@pytest.fixture
def db(mocker):
    d=Database();mocker.patch.object(dm,'get_connection',return_value=d)
    d.raw.execute('ALTER TABLE accounts ADD COLUMN account_alias TEXT')
    d.raw.execute('ALTER TABLE assets ADD COLUMN ticker TEXT')
    d.raw.execute("UPDATE accounts SET account_alias='해외ETF직투계좌',deposit_usd=100000")
    d.raw.execute("UPDATE assets SET market='US',ticker='VT'")
    d.raw.execute("INSERT INTO portfolios(id) VALUES('other')")
    d.raw.execute("INSERT INTO accounts(id,portfolio_id,account_alias,deposit_krw,deposit_usd) VALUES('gold','other','금현물계좌',1000000,0)")
    d.raw.execute('''INSERT INTO assets(id,market,portfolio_id,ticker,allowed_accounts)
        VALUES('pdbc','US','p','PDBC','["acc"]'),('gold','KR','other','M04020000','["gold"]')''')
    d.commit()
    for aid,sid,qty,extra,currency in [('acc','ast',63,52,'USD'),('acc','pdbc',70,40,'USD'),('gold','gold',9,5,'KRW')]:
        for day,kind,amount in [('2026-09-28','INIT',qty),('2026-09-29','BUY',extra)]:
            ok,msg=dm.execute_trade(day,aid,sid,kind,amount,100,currency,1300);assert ok,msg
        d.raw.execute('UPDATE holdings SET quantity=? WHERE asset_id=?',(qty,sid));d.commit()
    yield d
    d.raw.close()


def report(db):
    return calculate(db.rows('trade_history'),db.rows('holdings'),baselines=repo.load(db.cursor(),'p')+repo.load(db.cursor(),'other'))


def test_one_time_prepare_apply_retry_and_rollback_preserve_three_books(db):
    before=deepcopy(db.state());assert len(report(db)['warnings'])==3
    plan=repair.prepare(dm._context());assert db.state()==before
    assert db.raw.execute('SELECT count(*) FROM bookkeeping_requests').fetchone()[0]==0
    result=repair.apply(dm._context(),plan)
    assert result['positions']==3 and db.state()==before and not report(db)['warnings']
    assert repair.apply(dm._context(),plan)==result and db.state()==before
    assert db.raw.execute('SELECT count(*) FROM bookkeeping_requests').fetchone()[0]==2  # two portfolio scopes
    repair.apply(dm._context(),plan,rollback=True)
    assert db.state()==before and len(report(db)['warnings'])==3
    repair.apply(dm._context(),plan,rollback=True)  # idempotent audit append


def test_wrong_target_or_last_stale_position_rolls_back_all_three(db):
    plan=repair.prepare(dm._context());bad=deepcopy(plan);bad['positions'][-1]['asset_id']='ast'
    with pytest.raises(ValueError,match='세 종목'):repair.apply(dm._context(),bad)
    bad=deepcopy(plan);bad['positions'][0]['book_token']='0'*64  # p follows other in lock order
    before=db.state()
    with pytest.raises(ValueError,match='장부가 변경'):repair.apply(dm._context(),bad)
    assert db.state()==before and db.raw.execute('SELECT count(*) FROM bookkeeping_requests').fetchone()[0]==0
    with pytest.raises(ValueError,match='세 종목'):repair.apply(dm._context(),{**plan,'positions':plan['positions'][:2]})


def test_sale_blocks_only_admin_rollback_and_undo_restores_basis(db):
    plan=repair.prepare(dm._context());repair.apply(dm._context(),plan);before=db.state()
    day=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    ok,msg=dm.execute_trade(day,'acc','ast','SELL',1,120,'USD',1400);assert ok,msg
    after=db.state();assert not report(db)['warnings']
    with pytest.raises(ValueError,match='매도 손익'):repair.apply(dm._context(),plan,rollback=True)
    assert db.state()==after and len(repo.load(db.cursor(),'p'))==2 and len(repo.load(db.cursor(),'other'))==1
    tid=max(db.rows('trade_history'),key=lambda t:t['trade_sequence'])['id']
    assert dm.delete_trade(tid)[0] and db.state()==before and not report(db)['warnings']


def test_app_has_no_opening_management_endpoints(mocker):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers.trades import router
    mocked=mocker.patch('backend.routers.trades._context',side_effect=AssertionError('No DB access'))
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        for path in ('/api/trades/realized/opening','/api/trades/realized/opening/revoke'):
            assert client.get(path,params={'portfolio_id':'p'}).status_code==404
            assert client.post(path,params={'portfolio_id':'p'},json={}).status_code==404
        assert 'realized_opening_protocol' not in client.get('/api/trades/capabilities').json()
    assert not mocked.called
