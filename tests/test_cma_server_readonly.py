"""Synthetic checks for the approved SSH reader: no remote IO in tests."""
import json
from types import SimpleNamespace
import pytest
from scripts import cma_server_readonly as reader


class Response:
    def __init__(self,body,status=200):self.body,self.status_code=body,status
    def json(self):return self.body


class Session:
    def __init__(self,auth=200,compare=200,count=1):
        self.headers={};self.calls=[];self.closed=False
        self.auth,self.compare,self.count=auth,compare,count
    def post(self,url,**kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append(('POST',url))
        if url==reader.BASE+'/api/auth/verify':
            assert kwargs['json']=={'password':'SYNTHETIC_PASSWORD'}
            return Response({'access_token':'SYNTHETIC_SESSION'},self.auth)
        assert url==reader.BASE+'/api/sync/namuh/compare'
        assert kwargs['json']=={'portfolio_id':'p','account_id':'cma-0'}
        return Response(dict(account_id='cma-0',book_krw=38036748,broker_krw=34074558,
            holdings_provided=True,holdings=[]),self.compare)
    def get(self,url,**kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append(('GET',url))
        if url==reader.BASE+'/api/portfolios/':
            return Response({'portfolios':[dict(id='p',name='미래 성장포트')]})
        if url==reader.BASE+'/api/accounts/':
            assert kwargs['params']=={'portfolio_id':'p'}
            return Response({'accounts':[dict(id='cma-'+str(i),account_type='CMA',
                deposit_krw=38036748,account_no='PRIVATE_ACCOUNT_NUMBER') for i in range(self.count)]})
        assert url==reader.BASE+'/api/activity/p'
        assert kwargs['params']['account_id']=='cma-0' and kwargs['params']['page_size']==100
        return Response(dict(total=1,pages=1,items=[dict(account_id='cma-0',event_date='2026-10-14',
            category='CASH',kind='WITHDRAW',currency='KRW',amount=200000,
            detail=dict(cash_applied=True,reported_available_krw=38072203,notes='PRIVATE_MEMO'))]))
    def close(self):self.closed=True


def scenario(monkeypatch,*,password=True,**kwargs):
    session=Session(**kwargs)
    monkeypatch.setattr(reader,'service_property',lambda name:{'ActiveState':'active','MainPID':'123'}[name])
    def path(value):
        if value=='/proc/123/environ':
            return SimpleNamespace(read_bytes=lambda:(b'APP_PASSWORD=SYNTHETIC_PASSWORD\0' if password else b'')+b'NAMUH_APP_KEY=PRIVATE_NH_KEY\0')
        assert value=='/opt/portfolio-rebalancer/current'
        return SimpleNamespace(resolve=lambda:SimpleNamespace(name='synthetic-release'))
    monkeypatch.setattr(reader,'Path',path)
    monkeypatch.setattr(reader,'ENV',SimpleNamespace(is_file=lambda:False))
    monkeypatch.setattr(reader.requests,'Session',lambda:session)
    return session


def test_only_existing_service_comparison_no_secret_or_raw_account_report(monkeypatch,capsys):
    session=scenario(monkeypatch)
    report=reader.main()
    assert report['state']=='READ_ONLY_COMPARISON_RECEIVED'
    assert report['difference_krw']=='-3962190' and not report['interest_confirmed']
    assert report['nh_compare_attempts']==1 and report['scoped_accounts_unchanged']
    assert len(session.calls)==5 and session.closed and not session.headers
    output=json.dumps(report)+capsys.readouterr().out
    for value in ('SYNTHETIC_PASSWORD','SYNTHETIC_SESSION','PRIVATE_ACCOUNT_NUMBER','PRIVATE_NH_KEY'):
        assert value not in output


def test_ledger_mode_cannot_repeat_nh_call_and_filters_private_notes(monkeypatch,capsys):
    session=scenario(monkeypatch)
    report=reader.main(ledger_only=True)
    assert report['state']=='SCOPED_LEDGER_READ_RECEIVED'
    assert report['history_total']==1 and report['history_complete']
    assert report['history'][0]['reported_available_krw']=='38072203'
    assert report['nh_compare_attempts']==report['ledger_write_requests']==0
    assert all('/sync/' not in url for _,url in session.calls)
    assert 'PRIVATE_MEMO' not in json.dumps(report)+capsys.readouterr().out


@pytest.mark.parametrize('kwargs,state,count',[
    ({'auth':401},'APP_AUTH_UNAVAILABLE',0),
    ({'count':2},'CMA_SELECTION_UNVERIFIED',0),
    ({'compare':502},'BROKER_COMPARISON_UNAVAILABLE',1),
])
def test_ambiguity_and_failures_never_retry_or_write(monkeypatch,kwargs,state,count):
    session=scenario(monkeypatch,**kwargs)
    report=reader.main()
    assert report['state']==state and report['nh_compare_attempts']==count
    assert report['direct_nh_token_requests']==report['ledger_write_requests']==report['service_changes']==0
    assert session.closed


def test_no_existing_configuration_fails_before_app_or_nh_login(monkeypatch):
    session=scenario(monkeypatch,password=False)
    report=reader.main()
    assert report['state']=='READ_ONLY_CHECK_FAILED' and not session.calls
    assert report['nh_compare_attempts']==0
