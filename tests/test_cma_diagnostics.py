import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from logic.cma_diagnostics import balance_diagnostics,public_diagnostics
from backend.routers import cma_diagnostics as router
from test_cma_interest import wire,NOW


def test_raw_names_accounts_messages_and_unknown_values_are_not_returned():
    raw=wire(0,[dict(iem_cd='NHKRCMA030',iem_nm='CMA PRIVATE_NAME',eal_amt=4800123,rsdl_qty=999)],drn_pbl_amt=4800123)
    raw['rsp_msg']='PRIVATE_MESSAGE'
    raw['Output_0'].update(act_no='PRIVATE_ACCOUNT',unknown_balance='PRIVATE_VALUE',APP_PASSWORD='PRIVATE_PASSWORD')
    result=public_diagnostics({**balance_diagnostics(raw,NOW),'raw':'PRIVATE_RAW'})
    text=json.dumps(result)
    for private in ('PRIVATE_NAME','PRIVATE_MESSAGE','PRIVATE_ACCOUNT','PRIVATE_VALUE','PRIVATE_PASSWORD','PRIVATE_RAW'):assert private not in text
    assert result['profile_verified'] is False
    assert result['cash_fields']['dca']['value']=='0'
    assert result['cash_fields']['drn_pbl_amt']['value']=='4800123'
    assert result['rows'][0]['evaluation_krw']=='4800123' and result['rows'][0]['quantity']=='999'
    assert any(f['name']=='unknown_balance' for f in result['header_fields'])


@pytest.mark.parametrize('raw',[None,[],{'Output_0':[],'Output_1':{}},wire('NaN',drn_pbl_amt=True)])
def test_malformed_or_nonfinite_data_remains_unverified(raw):
    result=public_diagnostics(balance_diagnostics(raw,NOW))
    assert not result['profile_verified']
    assert result['cash_fields'].get('dca',{}).get('value') is None


def test_diagnostics_are_bounded_even_for_large_replies():
    raw=wire(1,[dict(iem_nm='CMA',eal_amt=1)]*30)
    raw['Output_0'].update({f'unknown_{i}':i for i in range(200)})
    data=public_diagnostics(balance_diagnostics(raw,NOW))
    assert len(data['rows'])==20 and len(data['header_fields'])==100 and data['truncated']


def test_documented_net_assets_and_debts_remain_separate_reference_fields():
    raw=wire(0,drn_pbl_amt=4800123,nas_amt=4800123,tot_aet_amt=4800123,rba=0,lon_amt=0)
    data=public_diagnostics(balance_diagnostics(raw,NOW))
    assert data['cash_fields']['nas_amt']['value']=='4800123'
    assert data['cash_fields']['dca']['value']=='0'
    assert data['cash_fields']['lon_amt']['value']=='0'
    assert data['profile_verified'] is False


def test_independent_route_off_does_not_touch_broker_or_db(monkeypatch):
    monkeypatch.setenv('CMA_DIAGNOSTICS_ENABLED','0')
    monkeypatch.setattr(router,'probe',Mock(side_effect=AssertionError('IO must be unreachable')))
    app=FastAPI();app.include_router(router.router)
    assert TestClient(app).post('/api/cma-diagnostics/p/a').status_code==409


def test_scoped_probe_reuses_one_existing_provider_and_redacts_again():
    account=dict(id='a',account_type='CMA',account_no='PRIVATE_ACCOUNT',deposit_krw=100)
    provider=Mock(return_value=({'cma_diagnostics':{**balance_diagnostics(wire(),NOW),'password':'PRIVATE_PASSWORD'}},None))
    data=router.probe('p','a',accounts=lambda:[account.copy()],provider=provider)
    assert data['book_unchanged'] and data['ledger_write_performed'] is False
    assert 'PRIVATE_PASSWORD' not in json.dumps(data)
    provider.assert_called_once_with('PRIVATE_ACCOUNT')
    with pytest.raises(ValueError):router.probe('p','other',accounts=lambda:[account],provider=provider)
    assert provider.call_count==1


def test_statement_probe_is_scoped_and_has_no_income_schema_dependency(monkeypatch):
    from data.cma_nh import TRANSACTIONS
    monkeypatch.setenv('CMA_INTEREST_ENABLED','0')
    monkeypatch.setenv('CMA_INTEREST_WRITES_ENABLED','0')
    account=dict(id='a',account_type='CMA',account_no='PRIVATE_ACCOUNT',deposit_krw=100)
    raw=dict(complete=True,nh_calls=3,queries={TRANSACTIONS:dict(complete=True,pages=[],rows=[
        dict(trd_dt='20261015',int_amt=23,opi_cus_fnm='PRIVATE_PERSON',iem_nm='CMA PRIVATE_NAME')])})
    collector=Mock(return_value=raw)
    data=router.probe('p','a',accounts=lambda:[account.copy()],include_statement=True,collector=collector)
    assert data['book_unchanged'] and data['ledger_write_performed'] is False
    assert data['statement_diagnostics']['queries'][TRANSACTIONS]['rows'][0]['int_amt']=='23'
    assert 'PRIVATE' not in json.dumps(data)
    assert collector.call_count==1 and collector.call_args.args[0]=='PRIVATE_ACCOUNT'
    with pytest.raises(ValueError):
        router.probe('p','wrong',accounts=lambda:[account],include_statement=True,collector=collector)
    assert collector.call_count==1


def test_statement_query_is_explicit_and_default_stays_balance_only(monkeypatch):
    monkeypatch.setenv('CMA_DIAGNOSTICS_ENABLED','1')
    probe=Mock(return_value={'ledger_write_performed':False})
    monkeypatch.setattr(router,'probe',probe)
    app=FastAPI();app.include_router(router.router);http=TestClient(app)
    assert http.post('/api/cma-diagnostics/p/a').status_code==200
    assert probe.call_args.kwargs=={'include_statement':False}
    assert http.post('/api/cma-diagnostics/p/a?include_statement=true').status_code==200
    assert probe.call_args.kwargs=={'include_statement':True}


def test_diagnostic_endpoint_remains_authenticated(monkeypatch):
    from backend.security import ApiAuthenticationMiddleware
    monkeypatch.setenv('CMA_DIAGNOSTICS_ENABLED','1')
    monkeypatch.setattr(router,'probe',Mock(side_effect=AssertionError('unauthorized IO')))
    app=FastAPI();app.add_middleware(ApiAuthenticationMiddleware);app.include_router(router.router)
    assert TestClient(app).post('/api/cma-diagnostics/p/a').status_code==401
