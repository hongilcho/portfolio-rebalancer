from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data.repositories import cma
from backend.routers import cma as router
from logic import cma_policy
from test_cma_repository import book,proposal


def test_repository_money_operations_are_blocked_before_connection(monkeypatch):
    monkeypatch.setenv('CMA_INTEREST_WRITES_ENABLED','0')
    db=SimpleNamespace(connect=Mock(side_effect=AssertionError('No DB access')))
    with pytest.raises(ValueError,match='차단'):cma.commit(db,'p',{},None)
    with pytest.raises(ValueError,match='차단'):cma.undo(db,'p','a','i')
    with pytest.raises(ValueError,match='차단'):cma.initialize_interest(db,'p',{},None)
    with pytest.raises(ValueError,match='차단'):cma.undo_initial_interest(db,'p','a','i')
    assert db.connect.call_count==0


def test_global_write_switch_blocks_http_income_undo_and_auto_settings(book,monkeypatch):
    request=proposal(book)
    monkeypatch.setattr(router,'enabled',lambda:True)
    monkeypatch.setenv('CMA_INTEREST_WRITES_ENABLED','0')
    call=Mock(side_effect=AssertionError('No DB access'));monkeypatch.setattr(router,'perform',call)
    app=FastAPI();app.include_router(router.router);client=TestClient(app)
    assert client.post('/api/cma/p/income',json=request).status_code==409
    assert client.post('/api/cma/p/acc/income/i/undo').status_code==409
    assert client.put('/api/cma/p/acc/settings',json={'auto_apply':True}).status_code==409
    assert call.call_count==0 and book.balances()[0]==4800000


def test_production_profile_gate_cannot_be_activated_by_settings(book,monkeypatch):
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset())
    with pytest.raises(ValueError,match='프로필'):
        cma.configure(book.ctx,'p','acc',dict(enabled=True,auto_apply=True,max_auto_interest=100,movements_confirmed=True))


def test_manual_opt_in_does_not_substitute_for_bank_receipt(book):
    cma.configure(book.ctx,'p','acc',dict(enabled=True,auto_apply=True,max_auto_interest=1000,movements_confirmed=True))
    proposal(book,now=__import__('test_cma_interest').NOW.replace(hour=9))
    req=proposal(book,verified=False);req['automatic']=True
    with pytest.raises(ValueError,match='명세'):cma.commit(book.ctx,'p',req,__import__('test_cma_interest').NOW)
    assert book.balances()[0]==4800000


def test_manual_checkbox_cannot_replace_an_unverified_bank_statement(book):
    from test_cma_interest import NOW
    req=proposal(book,verified=False)
    with pytest.raises(ValueError,match='명세'):cma.commit(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4800000


def test_provider_cannot_inject_a_reconciliation_receipt(book):
    from test_cma_interest import NOW,wire
    from logic.cma_interest import observe_balance
    current=cma.read_book(book.ctx,'p','acc')
    obs=cma.record_observation(book.ctx,'p','acc',{**observe_balance(wire(),NOW),'reconciliation':{'status':'MATCHED'}},current['book_token'])
    assert obs['reconciliation'] is None


@pytest.mark.parametrize('currency,kind,delta',[('USD','DEPOSIT',None),('KRW','INTERNAL_TRANSFER','-99')])
def test_reconciliation_cannot_treat_usd_or_mismatched_transfer_as_krw(book,monkeypatch,currency,kind,delta):
    from test_cma_reconciliation import statement
    from test_cma_interest import NOW,wire
    from logic.cma_interest import observe_balance
    from data.repositories import activity
    row=dict(id='movement',event_date=NOW.date().isoformat(),category='CASH',currency=currency,
             kind=kind,amount=100,detail=dict(cash_applied=True,delta_krw=delta))
    monkeypatch.setattr(activity,'read_page',lambda *a,**k:dict(pages=1,items=[row]))
    current=cma.read_book(book.ctx,'p','acc')
    evidence={**observe_balance(wire(),NOW),'statement':statement()}
    assert cma.reconciliation_for(book.ctx,'p','acc',current,evidence)['status']=='LEDGER_UNVERIFIED'
