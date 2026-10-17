from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
from data.cma_nh import snapshot,public_snapshot,CMAReadError,ORIGIN,BALANCE,TRANSACTIONS,MOVEMENTS

NOW=datetime(2026,10,15,10,tzinfo=timezone.utc)


def response(data,headers=None,status=200):
    return SimpleNamespace(status_code=status,content=json.dumps(data).encode(),json=lambda:data,headers=headers or {})


def client():
    return SimpleNamespace(base_url=ORIGIN,app_key='PRIVATE_KEY',app_secret='PRIVATE_SECRET',
        get_access_token=Mock(return_value='PRIVATE_TOKEN'),_throttle=Mock())


def wire(rows=None):return dict(rsp_cd='00000',rsp_msg='조회가 완료되었습니다.',Output_0=[] if rows is None else rows)


def test_existing_client_and_fixed_read_paths_with_cma_inclusive_history():
    c=client();post=Mock(side_effect=[response(wire()),response(wire()),response(wire({'dca':100}))])
    value=snapshot(c,'123-45678901','2026-10-14','2026-10-15',post=post,clock=lambda:NOW)
    assert value['complete'] and value['nh_calls']==3
    assert [call.args[0] for call in post.call_args_list]==[ORIGIN+TRANSACTIONS,ORIGIN+MOVEMENTS,ORIGIN+BALANCE]
    first=post.call_args_list[0].kwargs
    assert first['json']['Input_0']['iqr_rge_cd']=='2'
    assert first['headers']['Authorization']=='Bearer PRIVATE_TOKEN'
    assert first['headers']['x-client-id']=='PRIVATE_KEY'
    assert first['verify'] is True and first['allow_redirects'] is False
    assert c.get_access_token.call_count==1 and c._throttle.call_count==3


def test_complete_history_follows_exact_cursor_and_flag():
    first=response(wire([{'trd_amt':10}]),{'cts':'page1','cts_flag':'Y'})
    last=response(wire([{'trd_amt':20}]),{'cts':'same-final-key','cts_flag':'N'})
    post=Mock(side_effect=[first,last,response(wire()),response(wire({}))])
    value=snapshot(client(),'12345678901','2026-10-15','2026-10-15',post=post)
    assert len(value['queries'][TRANSACTIONS]['rows'])==2
    assert post.call_args_list[1].kwargs['headers']['cts']=='page1'
    assert post.call_args_list[1].kwargs['headers']['cts_flag']=='Y'


@pytest.mark.parametrize('headers',[{'cts_flag':'Y'},{'cts':'key'}, {'cts_flag':'MAYBE'}])
def test_ambiguous_or_missing_continuation_is_not_complete(headers):
    post=Mock(return_value=response(wire(),headers))
    with pytest.raises(CMAReadError):snapshot(client(),'12345678901','2026-10-15','2026-10-15',post=post)
    assert post.call_count==1


def test_repeated_and_over_budget_cursors_stop_without_retries():
    post=Mock(return_value=response(wire(),{'cts':'repeated','cts_flag':'Y'}))
    with pytest.raises(CMAReadError,match='PAGINATION_REPEATED'):
        snapshot(client(),'12345678901','2026-10-15','2026-10-15',post=post)
    assert post.call_count==2
    post=Mock(side_effect=[response(wire(),{'cts':str(i),'cts_flag':'Y'}) for i in range(3)])
    with pytest.raises(CMAReadError,match='PAGINATION_LIMIT'):
        snapshot(client(),'12345678901','2026-10-15','2026-10-15',post=post)
    assert post.call_count==3


@pytest.mark.parametrize('status',[302,401,429,500])
def test_http_failure_has_no_credential_refresh_retry_or_body_leak(status):
    c=client();post=Mock(return_value=response({'private':'PRIVATE_DATA'},status=status))
    with pytest.raises(CMAReadError,match='NH_HTTP_'+str(status)):
        snapshot(c,'12345678901','2026-10-15','2026-10-15',post=post)
    assert post.call_count==1 and c.get_access_token.call_count==1


def test_scope_and_range_rejected_before_any_credentials_or_http():
    c=client();post=Mock()
    with pytest.raises(CMAReadError):snapshot(c,'BAD','2026-10-15','2026-10-15',post=post)
    with pytest.raises(CMAReadError):snapshot(c,'12345678901','2026-01-01','2026-10-15',post=post)
    c.base_url='https://untrusted.example'
    with pytest.raises(CMAReadError):snapshot(c,'12345678901','2026-10-15','2026-10-15',post=post)
    c.get_access_token.assert_not_called();post.assert_not_called()


def test_public_diagnostics_preserve_financial_evidence_excluding_private_fields():
    row=dict(trd_dt='20261015',ral_trd_dt='20261015',cur_cd='KRW',trd_amt=1000,int_amt=23,tax_sum=3,
        sps_cd_krl_anm='CMA상환',iem_nm='CMA PRIVATE_NAME',iem_cd='NHKRCMA030',
        opi_cus_fnm='PRIVATE_PERSON',cli_pe_fnm='PRIVATE_PERSON',rks3='PRIVATE_ACCOUNT',rks4='PRIVATE_TOKEN')
    post=Mock(side_effect=[response(wire([row])),response(wire()),response(wire({'dca':100}))])
    result=public_snapshot(snapshot(client(),'12345678901','2026-10-15','2026-10-15',post=post,clock=lambda:NOW))
    assert 'PRIVATE' not in json.dumps(result)
    out=result['queries'][TRANSACTIONS]['rows'][0]
    assert out['int_amt']=='23' and out['tax_sum']=='3' and out['cma_marker']


def test_business_error_with_200_is_not_claimed_as_accounting_success():
    post=Mock(side_effect=[response(dict(rsp_cd='99999',rsp_msg='PRIVATE_ERROR',Output_0=[])),response(wire()),response(wire({}))])
    result=public_snapshot(snapshot(client(),'12345678901','2026-10-15','2026-10-15',post=post))
    status=result['queries'][TRANSACTIONS]['pages'][0]
    assert status['code']=='99999' and status['recognized_message'] is None
    assert 'PRIVATE_ERROR' not in json.dumps(result)


def test_partial_balance_is_never_reported_complete():
    post=Mock(side_effect=[response(wire()),response(wire()),response(wire({}),{'cts':'more','cts_flag':'Y'})])
    with pytest.raises(CMAReadError,match='BALANCE_PARTIAL'):
        snapshot(client(),'12345678901','2026-10-15','2026-10-15',post=post)
