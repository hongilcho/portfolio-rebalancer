from datetime import timedelta
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from backend.cma_interest import DailyCMA, poll, start_scheduler, existing_nh_balance
from backend.routers import cma as router
from data.repositories import cma
from logic.cma_interest import observe_balance
from test_cma_repository import book,proposal
from test_cma_interest import NOW,wire


def setup_worker(book,*,auto=True,cap=200,cash=4800123):
    cma.configure(book.ctx,'p','acc',dict(enabled=True,auto_apply=auto,max_auto_interest=cap,movements_confirmed=auto))
    clock=[NOW.replace(hour=9)]
    provider=Mock(side_effect=lambda *_:observe_balance(wire(cash),clock[0]))
    return DailyCMA(book.ctx,provider=provider,clock=lambda:clock[0]),clock,provider


def test_daily_worker_applies_stable_return_once_and_stops_for_day(book):
    worker,clock,provider=setup_worker(book)
    assert worker.tick()[0]['state']=='AWAITING_STABLE_RETURN'
    assert not worker.tick() and provider.call_count==1
    clock[0]=NOW
    assert worker.tick()[0]['state']=='STATEMENT_REQUIRED'
    assert book.balances()[0]==4800000 and provider.call_count==2
    clock[0]=NOW.replace(hour=15,minute=40)
    assert worker.tick()[0]['state']=='STATEMENT_REQUIRED' and provider.call_count==3


@pytest.mark.parametrize('auto,cap,state',[(False,200,'STATEMENT_REQUIRED'),(True,100,'STATEMENT_REQUIRED')])
def test_review_only_and_cap_exceeded_keep_book_unchanged(book,auto,cap,state):
    worker,clock,_=setup_worker(book,auto=auto,cap=cap)
    worker.tick();clock[0]=NOW
    assert worker.tick()[0]['state']==state and book.balances()[0]==4800000


def test_unknown_return_time_uses_later_slot_not_an_assumed_hour(book):
    worker,clock,provider=setup_worker(book)
    provider.side_effect=lambda *_:observe_balance(wire(0),clock[0])
    assert worker.tick()[0]['state']=='ZERO_UNVERIFIED'
    provider.side_effect=lambda *_:observe_balance(wire(),clock[0])
    clock[0]=NOW
    assert worker.tick()[0]['state']=='AWAITING_STABLE_RETURN'
    clock[0]=NOW.replace(hour=15,minute=40)
    assert worker.tick()[0]['state']=='STATEMENT_REQUIRED' and provider.call_count==3 and book.balances()[0]==4800000


def test_failure_private_errors_bounded_slots_and_no_immediate_retry(book):
    worker,clock,provider=setup_worker(book)
    provider.side_effect=RuntimeError('PRIVATE_TOKEN_ACCOUNT_NUMBER')
    assert worker.tick()[0]['state']=='CHECK_FAILED_REVIEW'
    assert not worker.tick() and provider.call_count==1
    clock[0]=NOW.replace(hour=20)
    assert not worker.tick() and provider.call_count==1 and book.balances()[0]==4800000


def test_poll_detects_book_change_during_broker_request(book):
    def provider(*_):
        book.raw.execute('UPDATE accounts SET deposit_krw=deposit_krw-200000');book.commit()
        return observe_balance(wire(),NOW)
    with pytest.raises(ValueError,match='조회 중'):
        poll(book.ctx,'p','acc',provider=provider)
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.observations').fetchone()[0]==0


def test_scheduler_disabled_never_creates_thread_or_reads_credentials(monkeypatch):
    monkeypatch.setenv('CMA_INTEREST_ENABLED','0')
    stop,thread=start_scheduler()
    assert thread is None and not stop.is_set()


def test_provider_uses_existing_singleton_for_statement_and_balance_not_a_new_client(monkeypatch):
    from data import data_manager,nh_api,cma_nh
    evidence=observe_balance(wire(),NOW)
    monkeypatch.setattr(data_manager,'get_all_accounts',lambda **_: [dict(id='acc',account_type='CMA',account_no='SYNTHETIC_ONLY')])
    fetch=Mock(return_value=dict(observed_at=NOW.isoformat(),queries={cma_nh.BALANCE:dict(pages=[dict(data=wire())])}))
    monkeypatch.setattr(cma_nh,'snapshot',fetch)
    monkeypatch.setattr(nh_api.nh_api_client,'get_access_token',Mock(side_effect=AssertionError('no separate token request')))
    result=existing_nh_balance('p','acc')
    assert {k:v for k,v in result.items() if k!='statement'}==evidence
    assert result['statement']=={'status':'PROFILE_UNVERIFIED'}
    assert fetch.call_count==1
    assert fetch.call_args.args[:2]==(nh_api.nh_api_client,'SYNTHETIC_ONLY')


def test_disabled_http_endpoints_do_not_touch_database_or_broker(monkeypatch):
    monkeypatch.setattr(router,'enabled',lambda:False)
    monkeypatch.setattr(router,'perform',Mock(side_effect=AssertionError('disabled IO')))
    app=FastAPI();app.include_router(router.router);client=TestClient(app)
    assert client.get('/api/cma/p').json()['enabled'] is False
    assert client.post('/api/cma/p/acc/observe').status_code==409


def test_enabled_preview_and_commit_http_serialize_and_replay_offline(book,monkeypatch):
    monkeypatch.setattr(router,'enabled',lambda:True)
    monkeypatch.setattr(router,'datetime',type('Clock',(),{'now':staticmethod(lambda *_:NOW)}))
    monkeypatch.setattr(router,'perform',lambda fn,*args:fn(book.ctx,*args))
    request=proposal(book)
    app=FastAPI();app.include_router(router.router);client=TestClient(app)
    result=client.post('/api/cma/p/income',json=request)
    assert result.status_code==200 and result.json()['saved']
    assert client.post('/api/cma/p/income',json=request).json()==result.json()
    assert book.balances()[0]==4800123
    assert client.post('/api/cma/p/income',json={**request,'automatic':True}).status_code==422


def test_actual_nh_cash_parser_with_fake_transport_preserves_legacy_total(monkeypatch):
    from data.nh_api import NamuhAPIClient
    from types import SimpleNamespace
    import requests
    client=NamuhAPIClient();monkeypatch.setattr(client,'get_access_token',lambda:'FAKE_TOKEN_ONLY')
    raw=wire(0,[dict(iem_cd='NHKRCMA030',iem_nm='CMA fixture',eal_amt=4800123)])
    response=SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:raw)
    post=Mock(return_value=response);monkeypatch.setattr(requests,'post',post)
    data,error=client.fetch_account_balance('SYNTHETIC_ONLY')
    assert error is None and data['deposit_krw']==4800123
    assert data['cma_evidence']['state']=='AWAITING_CASH_RETURN'
    assert post.call_count==1


def test_existing_legacy_withdrawable_fallback_is_preserved_but_not_income(monkeypatch):
    from data.nh_api import NamuhAPIClient
    from types import SimpleNamespace
    import requests
    client=NamuhAPIClient();monkeypatch.setattr(client,'get_access_token',lambda:'FAKE_TOKEN_ONLY')
    raw=wire(0,drn_pbl_amt='4800123')
    response=SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:raw)
    monkeypatch.setattr(requests,'post',Mock(return_value=response))
    data,error=client.fetch_account_balance('SYNTHETIC_ONLY')
    assert error is None and data['deposit_krw']==4800123
    evidence=data['cma_evidence']
    assert evidence['state']=='ZERO_UNVERIFIED' and evidence['withdrawable_krw']=='4800123'
    assert evidence['cash_krw']=='0' and evidence['total_krw']=='0'


@pytest.mark.parametrize('cap,state,balance',[(200,'APPLIED',4800123),(100,'AUTO_LIMIT_REVIEW',4800000)])
def test_verified_statement_pipeline_and_current_cap(book,monkeypatch,cap,state,balance):
    from test_cma_reconciliation import statement
    from data.repositories import activity
    monkeypatch.setattr(activity,'read_page',lambda *a,**k:dict(items=[],pages=1))
    worker,clock,provider=setup_worker(book,cap=cap)
    provider.side_effect=lambda *_:{**observe_balance(wire(),clock[0]),'statement':statement(clock[0])}
    worker.tick();clock[0]=NOW
    assert worker.tick()[0]['state']==state and book.balances()[0]==balance


def test_write_off_worker_never_posts_even_with_old_auto_policy(book,monkeypatch):
    worker,clock,_=setup_worker(book)
    monkeypatch.setenv('CMA_INTEREST_WRITES_ENABLED','0')
    worker.tick();clock[0]=NOW
    assert worker.tick()[0]['state']=='WRITE_DISABLED_REVIEW' and book.balances()[0]==4800000
