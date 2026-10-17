"""Run over approved SSH stdin: existing service API only, never app imports.

The only POSTs are existing app login and its read-only NH comparison.
Secrets stay in this process; reports contain no credentials/account numbers.
"""
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import re
import subprocess
import sys

import requests

BASE = 'http://127.0.0.1:8100'
UNIT = 'portfolio-api.service'
ENV = Path('/etc/portfolio-rebalancer/api.env')


def service_property(name):
    return subprocess.check_output(['systemctl','show',UNIT,'--property='+name,'--value'],
        text=True,stderr=subprocess.DEVNULL,timeout=10).strip()


def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)


def main(*,ledger_only=False):
    report=dict(checked_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
        source='running AWS service /api/sync/namuh/compare',
        nh_compare_attempts=0,ledger_write_requests=0,direct_nh_token_requests=0,
        deployments=0,service_changes=0,raw_balance_available=False,interest_confirmed=False)
    session=None
    try:
        assert service_property('ActiveState')=='active'
        pid=service_property('MainPID')
        assert re.fullmatch(r'[1-9][0-9]*',pid)
        process_env=dict(item.split(b'=',1) for item in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in item)
        password=process_env.get(b'APP_PASSWORD',b'').decode()
        report['app_password_source']='existing_service_environment'
        if not password and ENV.is_file():
            from dotenv import dotenv_values
            password=dotenv_values(ENV).get('APP_PASSWORD') or ''
            report['app_password_source']='existing_service_env_file'
        process_env.clear()
        assert password,'Missing existing app configuration'
        report['existing_service_active']=True
        report['existing_release']=Path('/opt/portfolio-rebalancer/current').resolve().name
        emit(dict(stage='EXISTING_SERVICE_CONFIGURATION_VERIFIED',credential_values_printed=False))
        session=requests.Session();session.trust_env=False
        response=session.post(BASE+'/api/auth/verify',json={'password':password},timeout=20,allow_redirects=False)
        password=None
        report['app_auth_http_status']=response.status_code
        if response.status_code!=200:
            report['state']='APP_AUTH_UNAVAILABLE'
            return report
        session.headers['Authorization']='Bearer '+response.json()['access_token']
        emit(dict(stage='EXISTING_APP_AUTHENTICATED',http_status=200))
        def get(path,params=None):
            response=session.get(BASE+path,params=params,timeout=20,allow_redirects=False)
            assert response.status_code==200
            return response.json()
        portfolios=get('/api/portfolios/')['portfolios']
        matches=[p for p in portfolios if p['name']=='미래 성장포트']
        if len(matches)!=1:
            report.update(state='PORTFOLIO_SELECTION_UNVERIFIED',portfolio_matches=len(matches))
            return report
        portfolio=matches[0]['id']
        def accounts():return get('/api/accounts/',{'portfolio_id':portfolio})['accounts']
        before=accounts()
        matches=[a for a in before if a['account_type']=='CMA']
        report['scoped_cma_accounts']=len(matches)
        if len(matches)!=1:
            report['state']='CMA_SELECTION_UNVERIFIED'
            return report
        account=matches[0]
        emit(dict(stage='SCOPED_CMA_SELECTED',portfolio='미래 성장포트',account_count=1))
        if ledger_only:
            # Scoped account history is a read-only transaction in this API.
            history=get('/api/activity/'+portfolio,dict(start_date='2026-10-14',end_date='2026-10-15',
                account_id=account['id'],include_cancelled='false',page_size=100,page=1))
            def numeric(value):
                if value is None or isinstance(value,bool):return None
                try:
                    number=Decimal(str(value))
                    return str(number) if number.is_finite() else None
                except Exception:return None
            rows=[]
            for item in history['items']:
                assert item['account_id']==account['id']
                detail=item.get('detail') or {}
                rows.append(dict(event_date=item['event_date'],category=item['category'],kind=item['kind'],
                    currency=item['currency'],amount=numeric(item['amount']),
                    delta_krw=numeric(detail.get('delta_krw')),cash_applied=detail.get('cash_applied'),
                    reported_available_krw=numeric(detail.get('reported_available_krw'))))
            after=accounts()
            canonical=lambda rows:json.dumps(sorted(rows,key=lambda a:str(a['id'])),sort_keys=True,default=str)
            report.update(state='SCOPED_LEDGER_READ_RECEIVED',portfolio_name='미래 성장포트',
                history_start='2026-10-14',history_end='2026-10-15',history_total=history['total'],
                history_complete=history.get('pages',1)==1,history=rows,
                current_book_krw=numeric(account['deposit_krw']),
                scoped_accounts_unchanged=canonical(before)==canonical(after))
            return report
        # This enters the existing running service/client, retaining its cache.
        # No NH client or token endpoint exists in this SSH process.
        report['nh_compare_attempts']=1
        response=session.post(BASE+'/api/sync/namuh/compare',
            json={'portfolio_id':portfolio,'account_id':account['id']},timeout=35,allow_redirects=False)
        report['compare_http_status']=response.status_code
        after=accounts()
        canonical=lambda rows:json.dumps(sorted(rows,key=lambda a:str(a['id'])),sort_keys=True,default=str)
        report['scoped_accounts_unchanged']=canonical(before)==canonical(after)
        if response.status_code!=200:
            report['state']='BROKER_COMPARISON_UNAVAILABLE'
            return report
        data=response.json()
        assert data['account_id']==account['id']
        cash=lambda x:Decimal(str(x))
        book,broker=cash(data['book_krw']),cash(data['broker_krw'])
        assert book.is_finite() and broker.is_finite()
        report.update(state='READ_ONLY_COMPARISON_RECEIVED',portfolio_name='미래 성장포트',
            book_krw=str(book),broker_comparison_krw=str(broker),difference_krw=str(broker-book),
            returned_holding_count=len(data.get('holdings',[])),holdings_provided=data.get('holdings_provided'),
            cma_evidence_in_response=isinstance(data.get('cma_evidence'),dict),
            note='Existing API returns a normalized balance; cash, sweep and withdrawal limits cannot be certified separately from this reply.')
        return report
    except Exception as exc:
        report.update(state='READ_ONLY_CHECK_FAILED',error_type=type(exc).__name__)
        return report
    finally:
        if session is not None:
            session.headers.pop('Authorization',None);session.close()


if __name__=='__main__':emit(main(ledger_only=sys.argv[1:]==['--ledger-only']))
