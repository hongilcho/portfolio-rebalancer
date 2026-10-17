"""Remote stdin inspection of the existing app; no imports, edits or NH calls."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import urllib.error


class ReadOnlyHTTPError(Exception):
    def __init__(self,path,status):self.path,self.status=path.split('?')[0],status


def main():
    unit='portfolio-api.service'
    pid=subprocess.check_output(['systemctl','show',unit,'--property=MainPID','--value'],text=True).strip()
    assert pid.isdigit() and int(pid)>0
    release=Path('/opt/portfolio-rebalancer/current').resolve()
    env=dict(v.split(b'=',1) for v in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in v)
    password=env.get(b'APP_PASSWORD',b'').decode();env.clear()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def call(path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request('http://127.0.0.1:8100'+path,
            data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            with opener.open(request,timeout=25) as response:return json.load(response)
        except urllib.error.HTTPError as exc:raise ReadOnlyHTTPError(path,exc.code) from None
    token=call('/api/auth/verify',{'password':password})['access_token'];password=None
    ports=[p for p in call('/api/portfolios/',token=token)['portfolios'] if p['name']=='미래 성장포트']
    assert len(ports)==1
    from urllib.parse import urlencode
    pid=str(ports[0]['id'])
    def account():
        rows=[a for a in call('/api/accounts/?'+urlencode({'portfolio_id':pid}),token=token)['accounts'] if a['account_type']=='CMA']
        assert len(rows)==1
        return rows[0]
    before=account()
    history=call('/api/activity/'+pid+'?'+urlencode(dict(start_date='2026-10-14',end_date='2026-10-15',
        account_id=before['id'],include_cancelled='false',page_size=100,page=1)),token=token)
    try:schema=call('/openapi.json',token=token)
    except ReadOnlyHTTPError as exc:
        if exc.status!=404:raise
        schema={'paths':{}}
    source=release/'data/nh_api.py'
    tree=ast.parse(source.read_text())
    methods=[n.name for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body if isinstance(n,ast.FunctionDef)]
    result=dict(release=release.name,release_unchanged=Path('/opt/portfolio-rebalancer/current').resolve()==release,
        nh_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),nh_methods=methods,
        cma_routes=[p for p in schema['paths'] if 'cma' in p.lower()],
        book_cash_krw=before['deposit_krw'],accounts_unchanged=before==account(),
        ledger_total=history['total'],ledger_complete=history.get('pages',1)==1,
        ledger=[dict(event_date=r['event_date'],kind=r['kind'],currency=r['currency'],amount=r['amount'],
            delta_krw=(r.get('detail') or {}).get('delta_krw'),cash_applied=(r.get('detail') or {}).get('cash_applied')) for r in history['items']],
        nh_calls=0,ledger_writes=0,service_changes=0)
    token=None
    return result


if __name__=='__main__':
    try:print(json.dumps(main(),ensure_ascii=True),flush=True)
    except ReadOnlyHTTPError as exc:print(json.dumps({'state':'READ_ONLY_HTTP_FAILED','path':exc.path,'status':exc.status}),flush=True)
    except Exception as exc:print(json.dumps({'state':'READ_ONLY_INSPECTION_FAILED','error_type':type(exc).__name__}),flush=True)
