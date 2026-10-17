"""The operator verifier may only use the existing app's read-only NH route."""
from copy import deepcopy
import json
from scripts import verify_cma_existing_connection as verifier


class Response:
    def __init__(self,data,status=200): self.data,self.status_code=data,status
    def json(self): return deepcopy(self.data)
    def raise_for_status(self):
        if self.status_code!=200: raise RuntimeError('Synthetic HTTP failure')


class Session:
    def __init__(self,status=200,count=1,changed=False,compare_status=200):
        self.headers={}; self.calls=[]; self.status=status; self.count=count
        self.changed=changed; self.compare_status=compare_status; self.account_reads=0
    def post(self,url,**kwargs):
        self.calls.append(('POST',url))
        if url.endswith('/api/auth/verify'):
            return Response({'access_token':'synthetic-app-session'},self.status)
        assert url==verifier.BASE+'/api/sync/namuh/compare'
        assert kwargs['json']=={'portfolio_id':'p','account_id':'cma-0'}
        return Response(dict(account_id='cma-0',book_krw=4800000,broker_krw=4800123,
            holdings_provided=True,holdings=[]),self.compare_status)
    def get(self,url,**kwargs):
        self.calls.append(('GET',url))
        if url.endswith('/api/portfolios/'):
            return Response({'portfolios':[dict(id='p',name='미래 성장포트')]})
        assert url==verifier.BASE+'/api/accounts/'
        assert kwargs['params']=={'portfolio_id':'p'}
        self.account_reads+=1
        return Response({'accounts':[dict(id='cma-'+str(i),account_type='CMA',
            account_no='synthetic-private-number',deposit_krw=4800000+int(self.changed and self.account_reads==2))
            for i in range(self.count)]})
    def close(self): pass


def run(monkeypatch,**kwargs):
    session=Session(**kwargs)
    monkeypatch.setattr(verifier.requests,'Session',lambda:session)
    return verifier.main(),session


def test_only_one_read_only_broker_comparison_and_no_secret_in_report(monkeypatch):
    report,session=run(monkeypatch)
    assert report['nh_compare_attempts']==1 and report['difference_krw']=='123'
    assert report['scoped_accounts_unchanged'] and not report['interest_confirmed']
    assert not report['raw_cash_sweep_envelope_available']
    assert report['ledger_write_requests']==report['direct_nh_token_requests']==0
    assert len(session.calls)==5
    assert 'Authorization' not in session.headers
    assert 'synthetic-private-number' not in json.dumps(report)
    assert 'synthetic-app-session' not in json.dumps(report)


def test_bad_app_login_never_contacts_nh(monkeypatch):
    report,session=run(monkeypatch,status=401)
    assert report['state']=='APP_AUTH_UNAVAILABLE' and report['nh_compare_attempts']==0
    assert len(session.calls)==1


def test_multiple_cma_accounts_never_guesses_account_or_contacts_nh(monkeypatch):
    report,session=run(monkeypatch,count=2)
    assert report['state']=='CMA_SELECTION_UNVERIFIED' and report['nh_compare_attempts']==0
    assert len(session.calls)==3


def test_read_only_does_not_claim_unchanged_when_concurrent_book_changes(monkeypatch):
    report,_=run(monkeypatch,changed=True)
    assert not report['scoped_accounts_unchanged']
    assert not report['interest_confirmed']


def test_nh_failure_is_not_retried_or_replaced_with_direct_token(monkeypatch):
    report,session=run(monkeypatch,compare_status=502)
    assert report['state']=='BROKER_COMPARISON_UNAVAILABLE'
    assert report['nh_compare_attempts']==1 and len(session.calls)==5
