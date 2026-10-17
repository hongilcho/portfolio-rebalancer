"""One diagnostic request through an existing app session; no ledger writes.

The prepared bundle prepends the pure redactor, making SSH stdin self-contained.
Do not execute against a server before operational verification is approved.
"""
import json
from pathlib import Path
import re
import subprocess
import requests

if 'public_diagnostics' not in globals():
    from logic.cma_diagnostics import public_diagnostics

BASE='http://127.0.0.1:8100'


def main(*,password=None,session=None):
    report=dict(state='NOT_STARTED',diagnostic_requests=0,ledger_write_requests=0,
        order_requests=0,direct_nh_token_requests=0,service_changes=0)
    try:
        if password is None:
            pid=subprocess.check_output(['systemctl','show','portfolio-api.service','--property=MainPID','--value'],text=True).strip()
            assert re.fullmatch(r'[1-9][0-9]*',pid)
            values=dict(row.split(b'=',1) for row in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in row)
            password=values.get(b'APP_PASSWORD',b'').decode();values.clear()
        assert password,'Existing app configuration required'
        session=session or requests.Session();session.trust_env=False
        response=session.post(BASE+'/api/auth/verify',json={'password':password},timeout=20,allow_redirects=False)
        password=None
        report['auth_http_status']=response.status_code
        if response.status_code!=200:
            report['state']='APP_AUTH_UNAVAILABLE';return report
        session.headers['Authorization']='Bearer '+response.json()['access_token']
        def get(path,params=None):
            response=session.get(BASE+path,params=params,timeout=20,allow_redirects=False)
            assert response.status_code==200
            return response.json()
        ports=[p for p in get('/api/portfolios/')['portfolios'] if p['name']=='미래 성장포트']
        assert len(ports)==1
        pid=str(ports[0]['id']);assert re.fullmatch(r'[A-Za-z0-9_-]{1,100}',pid)
        def selected():
            rows=[a for a in get('/api/accounts/',{'portfolio_id':pid})['accounts'] if a['account_type']=='CMA']
            assert len(rows)==1
            return rows[0]
        before=selected();aid=str(before['id']);assert re.fullmatch(r'[A-Za-z0-9_-]{1,100}',aid)
        report['diagnostic_requests']=1
        response=session.post(BASE+'/api/cma-diagnostics/'+pid+'/'+aid,timeout=35,allow_redirects=False)
        report['diagnostic_http_status']=response.status_code
        after=selected();report['book_unchanged']=before==after
        if response.status_code!=200:
            report['state']='DIAGNOSTIC_UNAVAILABLE';return report
        data=response.json();assert data['account_id']==aid and data['ledger_write_performed'] is False
        report.update(state='DIAGNOSTIC_RECEIVED',diagnostics=public_diagnostics(data.get('diagnostics')))
        return report
    except Exception as exc:
        report.update(state='DIAGNOSTIC_CHECK_FAILED',error_type=type(exc).__name__)
        return report
    finally:
        if session is not None:session.headers.pop('Authorization',None);session.close()


if __name__=='__main__':print(json.dumps(main(),ensure_ascii=False),flush=True)
