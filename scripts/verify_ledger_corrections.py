"""Run only against a new trust-authenticated loopback PostgreSQL QA cluster.
Never reads private config or calls production services. Creates a fresh synthetic DB.
"""
import argparse
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import sys
from uuid import uuid4
parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,choices=[55438],default=55438)
args=parser.parse_args()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2.extensions import parse_dsn,make_dsn
from psycopg2 import sql
from psycopg2.extras import Json
original_connect=psycopg2.connect

def local_connect(dsn=None,*a,**kw):
    p=parse_dsn(dsn) if dsn else {};p.update(kw)
    if p.get('host')!='127.0.0.1' or str(p.get('port'))!='55438' or p.get('user')!='ledger_qa':
        raise RuntimeError('Only the separate ledger QA cluster is allowed')
    return original_connect(dsn,*a,**kw)
psycopg2.connect=local_connect
settings=dict(host='127.0.0.1',port=args.port,user='ledger_qa',dbname='postgres')
name='ledger_verify_'+uuid4().hex[:12]
admin=local_connect(**settings);admin.autocommit=True
with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close();settings['dbname']=name
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL=make_dsn(**settings),APP_PASSWORD='qa-only',NAMUH_APP_KEY='',NAMUH_APP_SECRET='',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
import requests
from curl_cffi import requests as curl

def blocked(*a,**kw):raise RuntimeError('No external HTTP during synthetic verification')
requests.sessions.Session.request=blocked;curl.Session.request=blocked
from data import data_manager as dm
from data.repositories import ledger_adjustments as repo,performance,activity,trades
from backend.routers.ledger_adjustments import Proposal
from backend.routers.nh_notices import Row,Batch
from data.repositories import nh_notices
ctx=dm._context()
dm.init_db();dm.init_db()
today=performance.today();baseline=today-timedelta(days=3);old=baseline-timedelta(days=5)
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd) VALUES('qa','QA-CMA','QA CMA','CMA','default',2000000,10)")
    c.execute("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES('qa_etf','QA ETF','QA01','KR','[\"qa\"]','default')")
    conn.commit()
frozen={'ledger':{'accounts':[{'id':'qa','deposit_krw':2000000,'deposit_usd':10}],'holdings':[]},'fx':{'rate':1400},'prices':{'qa_etf':{'price_krw':100}}}
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute('INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload,close_started_on) VALUES(%s,%s,%s,%s,%s)',('default',baseline,2014000,Json(frozen),today+timedelta(days=1)))
    for d in [baseline,baseline+timedelta(days=1),baseline+timedelta(days=2)]:
        c.execute('INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES(%s,%s,%s,%s,%s)',('default',d,2014000,Json(frozen),'baseline' if d==baseline else 'close'))
    conn.commit()

def get_value(query,params=()):
    with dm.get_connection() as conn,conn.cursor() as c:c.execute(query,params);return c.fetchone()[0]

def save(p,decisions=None):
    preview=repo.preview(ctx,'default',p)
    req=dict(request_id=str(uuid4()),token=preview['token'],proposal=p,decisions=decisions or {},confirmed=True)
    return repo.commit(ctx,'default',req)['id'],req

p=Proposal(kind='PAST_WITHDRAWAL',account_id='qa',event_date=old,amount=1000000,reason='QA missed historical withdrawal').model_dump(mode='json')
ident,request=save(p,{'baseline':'ERROR',str(baseline):'ERROR',str(baseline+timedelta(days=1)):'NORMAL'})
assert get_value("SELECT deposit_krw FROM accounts WHERE id='qa'")==1000000
assert repo.commit(ctx,'default',request)['id']==ident
report=performance.read(ctx,'default')
assert report['ledger_unconfirmed'] and report['daily_reports'][-1]['profit'] is None
page=activity.read_page(ctx,'default',old,today,category='ADJUST')
assert len(page['items'])==1 and page['items'][0]['detail']['correction_id']==ident
assert page['items'][0]['detail']['history_pending']
preview=repo.review_preview(ctx,'default',ident)
review=dict(request_id=str(uuid4()),token=preview['token'],decisions={h['key']:'ERROR' for h in preview['history']},confirmed=True)
repo.review(ctx,'default',ident,review);repo.review(ctx,'default',ident,review)
assert get_value("SELECT deposit_krw FROM accounts WHERE id='qa'")==1000000
assert not performance.read(ctx,'default')['ledger_unconfirmed']
repo.undo(ctx,'default',ident);repo.undo(ctx,'default',ident)
assert get_value("SELECT deposit_krw FROM accounts WHERE id='qa'")==2000000
assert get_value("SELECT baseline_value FROM performance_tracking WHERE portfolio_id='default'")==2014000
# Real account locking serializes identical concurrent requests; only one cash deduction.
from concurrent.futures import ThreadPoolExecutor
preview=repo.preview(ctx,'default',p);req=dict(request_id=str(uuid4()),token=preview['token'],proposal=p,decisions={},confirmed=True)
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(lambda _:repo.commit(ctx,'default',req),range(2)))
assert results[0]['id']==results[1]['id']
assert get_value("SELECT deposit_krw FROM accounts WHERE id='qa'")==1000000
repo.undo(ctx,'default',results[0]['id'])
# One stale request loses the race; no additional partial updates.
preview=repo.preview(ctx,'default',p)
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("UPDATE accounts SET deposit_krw=2000001 WHERE id='qa'");conn.commit()
try:repo.commit(ctx,'default',dict(request_id=str(uuid4()),token=preview['token'],proposal=p,decisions={},confirmed=True));raise AssertionError('stale accepted')
except ValueError:pass
# USD adjustment works without an earlier tracking state; own event cannot bypass correction undo.
u=Proposal(kind='CASH',account_id='qa',event_date=today,reason='QA USD opening reconciliation',currency='USD',balance=20,usd_average_rate=1350).model_dump(mode='json')
uid,_=save(u);assert get_value("SELECT cost_krw FROM usd_cash_state WHERE account_id='qa'")==27000
page=activity.read_page(ctx,'default',old,today)
assert len([r for r in page['items'] if r['detail'].get('correction_id')==uid])==1
assert not [r for r in page['items'] if r['category']=='USD']
repo.undo(ctx,'default',uid);assert get_value("SELECT COUNT(*) FROM usd_cash_state WHERE account_id='qa'")==0
# Holdings INIT audit anchor can represent zero and undo must restore absence.
h=Proposal(kind='HOLDING',account_id='qa',event_date=today,reason='QA quantity correction',asset_id='qa_etf',quantity=0,avg_price=0).model_dump(mode='json')
hid,_=save(h)
assert get_value("SELECT quantity FROM holdings WHERE account_id='qa'")==0
anchor=get_value("SELECT trade_id FROM ledger_adjustments WHERE id=%s",(hid,))
assert not trades.delete_trades(ctx,[anchor])[0]
repo.undo(ctx,'default',hid)
# Scheduler and correction take tracking/job locks in one order.
from data.repositories import close_jobs
from datetime import timezone
now=datetime.now(timezone.utc)
close_jobs.schedule(ctx,'default',[today],today)
job=close_jobs.claim(ctx,now+timedelta(seconds=1),'default');assert job
try:save(p);raise AssertionError('running close allowed')
except ValueError as e:assert '종가 수집' in str(e)
close_jobs.fail(ctx,job,now,'QA retry')
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("UPDATE performance_close_jobs SET inputs=%s WHERE portfolio_id='default'",(Json({'ledger':'stale QA'}),));conn.commit()
rid,_=save(p)
assert get_value("SELECT inputs FROM performance_close_jobs WHERE portfolio_id='default'") is None
repo.undo(ctx,'default',rid)
# Claim must skip a correction holding the tracking lock, rather than deadlock.
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("UPDATE performance_close_jobs SET next_attempt_at=%s WHERE portfolio_id='default'",(now,));conn.commit()
    c.execute("SELECT portfolio_id FROM performance_tracking WHERE portfolio_id='default' FOR UPDATE")
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(close_jobs.claim,ctx,now+timedelta(seconds=1),'default').result(timeout=5) is None
    conn.rollback()
# Old API overwrite routes fail before broker calls; broker comparison is read-only.
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.routers import ledger_adjustments as api_router,sync,holdings,rebalance,accounts,forex as forex_router
app=FastAPI()
for r in [api_router.router,sync.router,holdings.router,rebalance.router,accounts.router,forex_router.router]:app.include_router(r)
with TestClient(app) as client:
    assert client.post('/api/sync/namuh').status_code==410
    assert client.post('/api/holdings/save',json={'account_id':'qa','holdings':[],'deposit_krw':1,'deposit_usd':0}).status_code==410
    assert client.post('/api/rebalance/apply-transfers',json={'transfer_plan':[]}).status_code==410
    assert client.post('/api/forex/qa/events',json={'kind':'RECONCILE','occurred_at':str(today)+'T12:00:00+09:00','rate':1400}).status_code==410
    meta={'account_no':'QA-CMA','account_alias':'QA renamed','account_type':'CMA'}
    assert client.put('/api/accounts/qa',json={**meta,'deposit_krw':1}).status_code==400
    assert client.put('/api/accounts/qa',json=meta).status_code==200
    assert get_value("SELECT deposit_krw FROM accounts WHERE id='qa'")==2000001
    sync.nh_api_client.fetch_account_balance=lambda _:({'deposit_krw':2000001},None)
    response=client.post('/api/sync/namuh/compare',json={'portfolio_id':'default','account_id':'qa'})
    assert response.status_code==200 and response.json()['holdings_provided'] is False
    assert get_value("SELECT deposit_krw FROM accounts WHERE id='qa'")==2000001
    body=Proposal(kind='CASH',account_id='qa',event_date=today,reason='QA UI confirmed',balance=2000001).model_dump(mode='json')
    response=client.post('/api/ledger-adjustments/default/preview',json=body);assert response.status_code==200
    bad=client.post('/api/ledger-adjustments/default',json={'request_id':str(uuid4()),'token':response.json()['token'],'proposal':body,'decisions':{},'confirmed':False})
    assert bad.status_code==422
print('PASS: PostgreSQL schema twice, atomic corrections/history/undo, concurrent idempotency, stale rejection, USD cost, quantity zero, paged audit SQL, API validation and read-only broker comparison; synthetic DB:',name)
