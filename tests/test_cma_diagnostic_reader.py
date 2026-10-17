import json
from scripts import cma_diagnostic_reader as reader
from logic.cma_diagnostics import balance_diagnostics
from test_cma_interest import NOW,wire


class Response:
    def __init__(self,body,status=200):self.body,self.status_code=body,status
    def json(self):return self.body


class Session:
    def __init__(self,auth=200,diag=200):self.headers={};self.calls=[];self.auth,self.diag=auth,diag
    def post(self,url,**kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append(url)
        if url.endswith('/api/auth/verify'):return Response({'access_token':'PRIVATE_SESSION'},self.auth)
        assert url==reader.BASE+'/api/cma-diagnostics/p/a'
        return Response(dict(account_id='a',ledger_write_performed=False,
            diagnostics={**balance_diagnostics(wire(),NOW),'raw_response':'PRIVATE_RAW'}),self.diag)
    def get(self,url,**kwargs):
        assert kwargs['allow_redirects'] is False
        if url.endswith('/api/portfolios/'):return Response({'portfolios':[dict(id='p',name='미래 성장포트')]})
        assert url.endswith('/api/accounts/') and kwargs['params']=={'portfolio_id':'p'}
        return Response({'accounts':[dict(id='a',account_type='CMA',account_no='PRIVATE_ACCOUNT',deposit_krw=10)]})
    def close(self):pass


def test_prepared_diagnostic_reader_posts_only_auth_and_one_diagnostic():
    session=Session();report=reader.main(password='PRIVATE_PASSWORD',session=session)
    assert report['state']=='DIAGNOSTIC_RECEIVED' and report['diagnostic_requests']==1
    assert len(session.calls)==2 and not session.headers
    assert report['ledger_write_requests']==report['order_requests']==0
    for private in ('PRIVATE_PASSWORD','PRIVATE_SESSION','PRIVATE_ACCOUNT','PRIVATE_RAW'):assert private not in json.dumps(report)


def test_disabled_diagnostic_is_not_retried_or_replaced_with_legacy_nh_call():
    session=Session(diag=409);report=reader.main(password='private',session=session)
    assert report['state']=='DIAGNOSTIC_UNAVAILABLE' and len(session.calls)==2


def test_failed_app_auth_never_calls_diagnostic():
    session=Session(auth=401);report=reader.main(password='private',session=session)
    assert report['state']=='APP_AUTH_UNAVAILABLE' and report['diagnostic_requests']==0
