"""Integration checks on a newly created, strictly loopback synthetic PostgreSQL DB."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
settings = json.loads((ROOT/'backups/local_validation/local_connection.json').read_text())
assert settings['host']=='127.0.0.1' and settings['port']==55437 and settings['dbname']=='postgres'
name = 'portfolio_workflow_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
admin = psycopg2.connect(**settings)
admin.autocommit=True
with admin.cursor() as c:
    c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close()
settings['dbname']=name
original_connect=psycopg2.connect
def guarded_connect(dsn=None,*args,**kwargs):
    parsed=parse_dsn(dsn) if dsn else {}
    parsed.update(kwargs)
    assert parsed['host']=='127.0.0.1' and str(parsed['port'])=='55437'
    return original_connect(dsn,*args,**kwargs)
psycopg2.connect=guarded_connect
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL=make_dsn(**settings),NAMUH_APP_KEY='',NAMUH_APP_SECRET='')
from data import data_manager as dm
from backend.routers import plans
from fastapi import FastAPI
from fastapi.testclient import TestClient
dm.init_db()
dm.init_db()
with dm.get_connection() as conn, conn.cursor() as c:
    c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw) VALUES('a','QA','QA','GENERAL','default',1000000)")
    c.execute("INSERT INTO assets(id,name,ticker,market,portfolio_id,allowed_accounts) VALUES('s','QA','QA','KR','default','[\"a\"]')")
    conn.commit()
assert dm.execute_trade('2026-10-01','a','s','BUY',1,100,'KRW',1)[0]
app=FastAPI()
app.include_router(plans.router)
client=TestClient(app)
payload={'name':'QA plan','scenario':'NEW_CASH','new_cash_krw':0,'drift_threshold':5,
         'trade_plan':[{'account_id':'a','asset_id':'s','account_alias':'QA','asset_name':'QA','type':'BUY','qty':3,'price':100,'total_krw':300}]}
def call(method,path,expected=200,**kwargs):
    response=getattr(client,method)(path,**kwargs)
    assert response.status_code==expected, (response.status_code,response.text)
    return response.json()
first=call('post','/api/plans/default',json=payload)['id']
second=call('post','/api/plans/default',json=payload)['id']
before=dm.get_trade_history()
old=before[0]['id']
call('post',f'/api/plans/default/{first}/links',400,json={'line_no':0,'trade_id':old})
assert dm.execute_trade('2026-10-02','a','s','BUY',2,110,'KRW',1)[0]
new=next(t['id'] for t in dm.get_trade_history() if t['trade_date']=='2026-10-02')
call('post',f'/api/plans/default/{first}/links',json={'line_no':0,'trade_id':new})
call('post',f'/api/plans/default/{first}/links',json={'line_no':0,'trade_id':new})
call('post',f'/api/plans/default/{second}/links',400,json={'line_no':0,'trade_id':new})
call('post',f'/api/plans/wrong/{first}/links',400,json={'line_no':0,'trade_id':new})
found=call('get','/api/plans/default')
assert next(p for p in found['plans'] if p['id']==first)['links'][0]['quantity']==2
assert not any(t['id']==new for t in found['candidates'])
call('patch',f'/api/plans/default/{first}',json={'archived':True})
call('patch',f'/api/plans/default/{first}',json={'archived':False})
call('delete',f'/api/plans/default/{first}/links/{new}')
call('post',f'/api/plans/default/{second}/links',json={'line_no':0,'trade_id':new})
assert dm.delete_trade(new)[0]
assert next(p for p in call('get','/api/plans/default')['plans'] if p['id']==second)['links']==[]
assert dm.get_trade_history()==before
print('PASS plan round-trip, scope, pre-save exclusion, idempotent linking, unique allocation, unlink, archive/restore, actual deletion cascade')
from backend.routers import performance as perf
from backend.services import market_service
market_service.get_prices=lambda **_: ([{'id':'s','price_krw':110}],{'s':110})
market_service.request_snapshot=lambda: {'usd_krw':1400,'rate_source':'QA'}
market_service.request_status=lambda: {'updated_at':datetime.now(timezone.utc).isoformat(),'stale':False,'refreshing':False,'refresh_failed':False}
app.include_router(perf.router)
day=(datetime.now(timezone.utc)+__import__('datetime').timedelta(hours=9)).date().isoformat()
call('post','/api/performance/default/start')
call('post','/api/performance/default/start',400)
state=call('get','/api/performance/default')
assert state['tracking']['baseline_value']>0 and len(state['snapshots'])==1
with dm.get_connection() as conn, conn.cursor() as c:
    c.execute("SELECT deposit_krw FROM accounts WHERE id='a'")
    cash=c.fetchone()[0]
f={'request_id':'QA-request-0001','account_id':'a','event_date':day,'direction':'DEPOSIT','currency':'KRW','native_amount':1000,'exchange_rate':1,'notes':'Synthetic external flow'}
fid=call('post','/api/performance/default/flows',json=f)['id']
assert call('post','/api/performance/default/flows',json=f)['id']==fid
call('post','/api/performance/default/flows',400,json={**f,'native_amount':2000})
call('post','/api/performance/default/flows',400,json={**f,'request_id':'QA-future','event_date':'2099-01-01'})
call('post','/api/performance/default/flows',400,json={**f,'account_id':'other'})
call('post','/api/performance/other/flows',400,json=f)
state=call('get','/api/performance/default')
assert len(state['flows'])==1 and state['tracking']['revision']==1
snap=state['snapshots'][-1]
confirmation={'revision':state['tracking']['revision'],'through':snap['snapshot_date'],'value':snap['value_krw']}
call('post','/api/performance/default/confirm',400,json={**confirmation,'revision':0})
call('post','/api/performance/default/confirm',400,json={**confirmation,'value':confirmation['value']+1})
call('post','/api/performance/default/confirm',json=confirmation)
assert call('get','/api/performance/default')['tracking']['confirmed_revision']==1
market_service.get_prices=lambda **_: ([{'id':'s','price_krw':120}],{'s':120})
call('post','/api/performance/default/snapshot')
assert call('get','/api/performance/default')['tracking']['confirmed_through']<day
call('post','/api/performance/default/confirm',400,json=confirmation)
market_service.get_prices=lambda **_: ([{'id':'s','price_krw':110}],{'s':110})
call('post','/api/performance/default/snapshot')
call('patch',f'/api/performance/default/flows/{fid}',json={'voided':True})
assert call('get','/api/performance/default')['tracking']['revision']==2
call('patch',f'/api/performance/default/flows/{fid}',json={'voided':False})
assert call('get','/api/performance/default')['tracking']['revision']==3
call('post','/api/performance/default/snapshot')
assert len(call('get','/api/performance/default')['snapshots'])==1
saved=call('get','/api/performance/default')['snapshots']
market_service.request_status=lambda: {'updated_at':None,'stale':True}
assert call('post','/api/performance/default/snapshot')['saved'] is False
assert call('get','/api/performance/default')['snapshots']==saved
market_service.request_status=lambda: {'updated_at':datetime.now(timezone.utc).isoformat(),'stale':False}
market_service.get_prices=lambda **_: ([],{})
call('post','/api/performance/default/snapshot',400)
assert call('get','/api/performance/default')['snapshots']==saved
with dm.get_connection() as conn, conn.cursor() as c:
    c.execute("SELECT deposit_krw FROM accounts WHERE id='a'")
    assert c.fetchone()[0]==cash
assert dm.get_trade_history()==before
print('PASS performance opt-in, immutable baseline, one daily snapshot, retry identity, scope/date guards, reversible flows, confirmation revisions, stale/missing-price preservation, unchanged cash/trades')
print('Synthetic local database:',name)
