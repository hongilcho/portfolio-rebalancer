"""One read-only comparison through the existing AWS application's NH client.

No direct NH client, token mint, bookkeeping endpoint or environment change.
Only an existing app password is loaded; response credentials stay in memory.
"""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = 'https://portfolio-rebalancer-api.duckdns.org'


def main():
    from backend import config
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(),
                  source='existing AWS /api/sync/namuh/compare',
                  nh_compare_attempts=0, ledger_write_requests=0,
                  direct_nh_token_requests=0, deployments=0)
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(BASE+'/api/auth/verify', json={'password':config.APP_PASSWORD}, timeout=20)
        report['app_auth_status'] = response.status_code
        if response.status_code != 200:
            report['state'] = 'APP_AUTH_UNAVAILABLE'
            return report
        session.headers['Authorization'] = 'Bearer '+response.json()['access_token']
        response = session.get(BASE+'/api/portfolios/', timeout=20)
        response.raise_for_status()
        matches = [p for p in response.json()['portfolios'] if p['name']=='미래 성장포트']
        if len(matches) != 1:
            report['state'] = 'PORTFOLIO_SELECTION_UNVERIFIED'
            return report
        pid = matches[0]['id']
        def accounts():
            r = session.get(BASE+'/api/accounts/', params={'portfolio_id':pid}, timeout=20)
            r.raise_for_status()
            return r.json()['accounts']
        before = accounts()
        candidates = [a for a in before if a['account_type']=='CMA']
        report['scoped_cma_accounts'] = len(candidates)
        if len(candidates) != 1:
            report['state'] = 'CMA_SELECTION_UNVERIFIED'
            return report
        account = candidates[0]
        report['nh_compare_attempts'] = 1
        response = session.post(BASE+'/api/sync/namuh/compare',
                                json={'portfolio_id':pid,'account_id':account['id']}, timeout=30)
        report['compare_http_status'] = response.status_code
        after = accounts()
        report['scoped_accounts_unchanged'] = before == after
        if response.status_code != 200:
            report['state'] = 'BROKER_COMPARISON_UNAVAILABLE'
            return report
        data = response.json()
        assert data['account_id']==account['id']
        report.update(state='READ_ONLY_COMPARISON_RECEIVED', portfolio_name='미래 성장포트',
            book_krw=str(Decimal(str(data['book_krw']))),
            broker_comparison_krw=str(Decimal(str(data['broker_krw']))),
            difference_krw=str(Decimal(str(data['broker_krw']))-Decimal(str(data['book_krw']))),
            holdings_provided=data.get('holdings_provided'),
            returned_holding_count=len(data.get('holdings',[])),
            raw_cash_sweep_envelope_available=False,
            interest_confirmed=False,
            note='Legacy comparison combines cash and CMA products; this response alone cannot certify returned cash or nightly timing.')
        return report
    except Exception as exc:
        report.update(state='CHECK_FAILED', error_type=type(exc).__name__)
        return report
    finally:
        session.headers.pop('Authorization',None)
        session.close()


if __name__ == '__main__':
    result = main()
    (ROOT/'docs/cma-existing-connection-evidence.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
