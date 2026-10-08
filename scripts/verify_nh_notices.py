"""NH cash batches on a fresh loopback PostgreSQL; never reads production settings."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,date
from decimal import Decimal
import json,os,sys
from pathlib import Path
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn,parse_dsn
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
settings=json.loads((ROOT/'backups/local_validation/local_connection.json').read_text())
assert settings['host']=='127.0.0.1' and settings['port']==55437 and settings['dbname']=='postgres'
name='portfolio_nh_'+datetime.now().strftime('%Y%m%d_%H%M%S')
admin=psycopg2.connect(**settings);admin.autocommit=True
with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close();settings['dbname']=name
original_connect=psycopg2.connect
def guarded_connect(dsn=None,*args,**kwargs):
    parsed=parse_dsn(dsn) if dsn else {};parsed.update(kwargs)
    assert parsed['host']=='127.0.0.1' and str(parsed['port'])=='55437'
    return original_connect(dsn,*args,**kwargs)
psycopg2.connect=guarded_connect
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL=make_dsn(**settings),NAMUH_APP_KEY='',NAMUH_APP_SECRET='',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
import requests
from curl_cffi import requests as curl_requests
def blocked(*_,**__):raise AssertionError('QA cannot call an external market')
requests.sessions.Session.request=blocked;curl_requests.Session.request=blocked
from data import data_manager as dm
from data.repository_context import RepositoryContext
from data.repositories import nh_notices,forex,performance,trades
from backend.routers.nh_notices import Batch,Row,router
from fastapi import FastAPI
from fastapi.testclient import TestClient
ctx=RepositoryContext(dm.get_connection,dm.generate_id,lambda:None)
dm.init_db();dm.init_db()
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("INSERT INTO portfolios(id,name) VALUES('p','Synthetic NH QA'),('other','Foreign QA')")
    c.execute("""INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd)
      VALUES('a','QA-001','QA cash','GENERAL','p',4,10),('isa','QA-002','QA ISA','ISA','p',190000,0),
      ('source','QA-003','QA transfer','GENERAL','p',1000000,0),('foreign','QA-004','Other','GENERAL','other',0,0)""")
    c.execute("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES('bond','QA bond','0085P0','KR','[\"isa\"]','p')")
    c.execute("INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,original_avg_price) VALUES('legacy-h','isa','bond',3,8000,8000)")
    c.execute("""INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload,close_started_on)
      VALUES('p','2026-01-01',1000000,'{}','2026-01-01')""")
    c.execute("""INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,amount_krw,currency,native_amount,exchange_rate)
      VALUES('legacy','p','a','QA-legacy-0001','2026-01-02',960000,'KRW',960000,1)""");conn.commit()
assert forex.record_cash_event(ctx,'a','OPENING','2026-01-01T12:00:00+09:00',rate=1300)[0]
def cash(aid='a'):
    with dm.get_connection() as conn,conn.cursor() as c:
        c.execute('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s',(aid,));return tuple(c.fetchone())
def row(kind,aid='a',**kw):return Row(kind=kind,account_id=aid,event_date='2026-01-02',**kw)
def batch(rows,key='QA-request-0001'):
    ids={r.account_id for r in rows}|{r.source_account_id for r in rows if r.source_account_id}
    return Batch(request_id=key,confirmed=True,rows=rows,expected_cash={a:dict(zip(('deposit_krw','deposit_usd'),cash(a))) for a in ids}).model_dump(mode='json')
def scenario(key='QA-request-0001'):
    return batch([row('DEPOSIT',krw_amount=960000,existing_flow_id='legacy',fingerprint='a'*64),
      row('EXCHANGE_IN',krw_amount=959997,usd_amount=717.31,quoted_rate=1338.33,fingerprint='b'*64)],key)
def fails(fn,phrase):
    try:fn()
    except ValueError as e:assert phrase in str(e),(phrase,str(e))
    else:raise AssertionError('Expected rejection')
data=scenario();bad=json.loads(json.dumps(data));bad['rows'][1]['krw_amount']=970000
fails(lambda:nh_notices.commit(ctx,'p',bad),'부족');assert cash()==(4,10)
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:nh_notices.commit(ctx,'p',data),range(2)))
assert results[0]==results[1] and cash()==(7,727.31)
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("SELECT COUNT(*) FROM nh_notice_batches");assert c.fetchone()[0]==1
    c.execute("SELECT COUNT(*) FROM performance_flows WHERE NOT voided");assert c.fetchone()[0]==1
    c.execute("SELECT cost_krw FROM usd_cash_state WHERE account_id='a'");assert c.fetchone()[0]==Decimal('972997')
    c.execute("SELECT occurred_at FROM usd_cash_events WHERE kind='EXCHANGE_IN'");assert c.fetchone()[0] is None
fails(lambda:performance.void_flow(ctx,'p','legacy',True),'묶음 취소')
assert not forex.undo_event(ctx,'a',results[0]['items'][1]['usd_event_id'])[0]
app=FastAPI();app.include_router(router);client=TestClient(app)
resp=client.get('/api/nh-notices/p/context?day=2026-01-02');assert resp.status_code==200,resp.text
info=resp.json();assert info['flows'][0]['cash_handled'] and 'audit' not in info['batches'][0]
resp=client.post('/api/nh-notices/p/batch',json=data);assert resp.status_code==200 and resp.json()==results[0],resp.text
assert client.post('/api/nh-notices/p/batch',json={**data,'confirmed':False}).status_code==422
nh_notices.undo(ctx,'p',results[0]['batch_id']);assert cash()==(4,10)
assert nh_notices.undo(ctx,'p',results[0]['batch_id'])=={'reversed':True}
# Exact pre-import legacy holding survives full batch undo.
rows=[row('DEPOSIT','isa',krw_amount=10000),row('BUY','isa',asset_id='bond',quantity=1,price=9320,broker_order_no='42954')]
buy=nh_notices.commit(ctx,'p',batch(rows,'QA-buy-0001'));assert cash('isa')==(190680,0)
assert not trades.delete_trades(ctx,[buy['items'][1]['trade_id']])[0]
nh_notices.undo(ctx,'p',buy['batch_id']);assert cash('isa')==(190000,0)
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("SELECT quantity,avg_price,original_avg_price FROM holdings WHERE id='legacy-h'");assert c.fetchone()==(3,8000,8000)
internal=nh_notices.commit(ctx,'p',batch([row('DEPOSIT',krw_amount=10000,external=False,source_account_id='source')],'QA-internal-0001'))
assert cash()==(10004,10) and cash('source')==(990000,0)
nh_notices.undo(ctx,'p',internal['batch_id']);assert cash()==(4,10) and cash('source')==(1000000,0)
adjust=nh_notices.commit(ctx,'p',batch([row('KRW_ADJUST',krw_amount=960004)],'QA-adjust-0001'))
assert cash()==(960004,10)
nh_notices.undo(ctx,'p',adjust['batch_id']);assert cash()==(4,10)
foreign=batch([row('KRW_ADJUST','foreign',krw_amount=1)],'QA-foreign-0001')
fails(lambda:nh_notices.commit(ctx,'p',foreign),'포트폴리오')
# Two distinct concurrent previews cannot both apply the same cash movement.
left=scenario('QA-race-left');right=scenario('QA-race-right')
def submit(payload):
    try:return nh_notices.commit(ctx,'p',payload)
    except ValueError as e:return str(e)
with ThreadPoolExecutor(max_workers=2) as pool:race=list(pool.map(submit,[left,right]))
assert sum(isinstance(r,dict) for r in race)==1 and cash()==(7,727.31)
print('PostgreSQL NH QA passed: atomic rollback, concurrent idempotency, stale previews, existing flow link, FX cost, API, scoped accounts, cash-only adjustment and audited undo. DB:',name)

# The history read does not replay transactions or double-count linked flows.
from data.repositories import activity
from backend.routers.activity import router as activity_router
app.include_router(activity_router)
before=cash()
start,end=date(2026,1,1),date(2026,1,2)
first=activity.read_page(ctx,'p',start,end)
assert first['total']==3 and len(first['items'])==3,first
linked=next(r for r in first['items'] if r['id']=='FLOW:legacy')
assert linked['batch_id'] and linked['detail']['cash_applied']
assert len([r for r in first['items'] if r['id'].startswith('NOTICE:')])==0
cancelled=activity.read_page(ctx,'p',start,end,include_cancelled=True)
assert any(r['id'].startswith('CANCELLED_BUY:') for r in cancelled['items'])
assert activity.read_page(ctx,'other',start,end)['total']==0
assert activity.read_page(ctx,'p',start,end,account='foreign')['total']==0
assert all(r['category']=='USD' for r in activity.read_page(ctx,'p',start,end,category='USD')['items'])
assert activity.read_page(ctx,'p',date(2026,2,1),date(2026,2,2))['total']==0
fails(lambda:activity.read_page(ctx,'p',end,start),'시작일')
for i in range(26):
    performance.add_flow(ctx,'p',dict(request_id='QA-page-'+str(i),account_id='isa',event_date=end,
      direction='DEPOSIT',currency='KRW',native_amount=i+1,exchange_rate=1,notes='Synthetic pagination'))
pages=[activity.read_page(ctx,'p',start,end,page=i) for i in (1,2)]
assert pages[0]['total']==29 and pages[0]['pages']==2
assert len(pages[0]['items'])==20 and len(pages[1]['items'])==9
assert not ({r['id'] for r in pages[0]['items']} & {r['id'] for r in pages[1]['items']})
assert activity.read_page(ctx,'p',start,end,page=999)['page']==2
resp=client.get('/api/activity/p?start_date=2026-01-01&end_date=2026-01-02&page=2')
assert resp.status_code==200 and len(resp.json()['items'])==9,resp.text
assert client.get('/api/activity/p?start_date=2026-01-02&end_date=2026-01-01').status_code==400
assert client.get('/api/activity/p?start_date=2026-01-01&end_date=2026-01-02&page_size=1000').status_code==422
assert cash()==before
print('Activity PostgreSQL QA passed: scoped read-only union, no linked-flow duplicates, reversals, date/account/category filters, stable page boundaries and API serialization.')

assert activity.read_page(ctx,'p',start,end,category='TRADE',include_cancelled=True,asset='bond')['total']==1
assert activity.read_page(ctx,'p',start,end,category='TRADE',include_cancelled=True,asset='foreign')['total']==0

# Upgrade an old populated CHECK in the disposable database, then initialize twice.
from data import workflow_schema
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute('ALTER TABLE nh_notice_items DROP CONSTRAINT nh_notice_items_kind_check')
    c.execute("ALTER TABLE nh_notice_items ADD CONSTRAINT nh_notice_items_kind_check CHECK(kind IN ('DEPOSIT','EXCHANGE_IN','BUY','KRW_ADJUST'))")
    workflow_schema.initialize(c);workflow_schema.initialize(c)
    c.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='nh_notice_items'::regclass AND conname='nh_notice_items_kind_check'")
    assert 'WITHDRAW' in c.fetchone()[0]
    c.execute("INSERT INTO portfolios(id,name) VALUES('growth','Synthetic growth'),('pool','Synthetic pool')")
    c.execute("""INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw)
        VALUES('cma','QA-X1','Growth CMA','GENERAL','growth',1000004),('liquid','QA-X2','Liquid cash','GENERAL','pool',100)""")
    c.execute("""INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload,close_started_on)
        VALUES('growth','2026-10-05',1000004,'{}','2026-10-05'),('pool','2026-10-05',100,'{}','2026-10-05')""")
    conn.commit()

def cross_batch(request,amount=1000000):
    return Batch(request_id=request,confirmed=True,rows=[Row(kind='WITHDRAW',account_id='cma',destination_account_id='liquid',external=False,cross_portfolio=True,event_date='2026-10-08',krw_amount=amount,fingerprint='d'*64)],expected_cash={'cma':dict(zip(('deposit_krw','deposit_usd'),cash('cma'))),'liquid':dict(zip(('deposit_krw','deposit_usd'),cash('liquid')))}).model_dump(mode='json')

cross=cross_batch('QA-cross-0001')
resp=client.post('/api/nh-notices/growth/batch',json=cross);assert resp.status_code==200,resp.text
saved=resp.json();assert saved['notice_count']==1 and len(saved['items'])==2
assert cash('cma')==(4,0) and cash('liquid')==(1000100,0)
assert nh_notices.commit(ctx,'growth',cross)==saved
with dm.get_connection() as conn,conn.cursor() as c:
    c.execute("SELECT portfolio_id,amount_krw FROM performance_flows WHERE account_id IN ('cma','liquid') ORDER BY portfolio_id")
    assert c.fetchall()==[('growth',-1000000),('pool',1000000)]
# Each side has one record, the other account's alias, and a shared cancellation batch.
for pid,aid,peer in [('growth','cma','Liquid cash'),('pool','liquid','Growth CMA')]:
    page=activity.read_page(ctx,pid,date(2026,9,1),date(2026,10,8))
    assert page['total']==1 and page['items'][0]['account_id']==aid
    assert page['items'][0]['description']=='포트폴리오 간 이체'
    assert page['items'][0]['detail']['peer_account']==peer
    assert page['items'][0]['batch_id']==saved['batch_id']
    info=nh_notices.read_context(ctx,pid,date(2026,10,8));assert info['flows'][0]['cash_handled']
    fails(lambda:performance.void_flow(ctx,pid,info['flows'][0]['id'],True),'묶음 취소')
# Repeating the opposite message is rejected, even with another raw fingerprint.
opposite=Batch(request_id='QA-cross-opposite',confirmed=True,rows=[Row(kind='DEPOSIT',account_id='liquid',source_account_id='cma',external=False,cross_portfolio=True,event_date='2026-10-08',krw_amount=1000000,fingerprint='e'*64)],expected_cash={'cma':{'deposit_krw':4,'deposit_usd':0},'liquid':{'deposit_krw':1000100,'deposit_usd':0}}).model_dump(mode='json')
fails(lambda:nh_notices.commit(ctx,'pool',opposite),'이미 반영')
resp=client.delete('/api/nh-notices/pool/batch/'+saved['batch_id']);assert resp.status_code==200,resp.text
assert cash('cma')==(1000004,0) and cash('liquid')==(100,0)
for pid in ('growth','pool'):
    assert activity.read_page(ctx,pid,date(2026,9,1),date(2026,10,8))['total']==0
    assert activity.read_page(ctx,pid,date(2026,9,1),date(2026,10,8),include_cancelled=True)['items'][0]['cancelled']
# Already reflected September withdrawals are history only; never overwrite current cash.
history=Batch(request_id='QA-withdraw-history',confirmed=True,rows=[Row(kind='WITHDRAW',account_id='cma',event_date='2026-09-30',occurred_at='2026-09-30T13:16:00+09:00',krw_amount=1000000,apply_cash=False,fingerprint='f'*64)],expected_cash={'cma':{'deposit_krw':1000004,'deposit_usd':0}}).model_dump(mode='json')
nh_notices.commit(ctx,'growth',history)
assert cash('cma')==(1000004,0)
page=activity.read_page(ctx,'growth',date(2026,9,1),date(2026,10,8))
assert page['total']==1 and page['items'][0]['kind']=='WITHDRAW' and not page['items'][0]['detail']['cash_applied']
# Both portfolios are locked in a consistent order; stale concurrent previews cannot both debit.
l=cross_batch('QA-cross-race-left',10);r=cross_batch('QA-cross-race-right',10)
def cross_submit(data):
    try:return nh_notices.commit(ctx,'growth',data)
    except ValueError as e:return str(e)
with ThreadPoolExecutor(max_workers=2) as pool:cross_race=list(pool.map(cross_submit,[l,r]))
assert sum(isinstance(r,dict) for r in cross_race)==1
assert cash('cma')==(999994,0) and cash('liquid')==(110,0)
print('Withdrawal/transfer PostgreSQL QA passed: old-schema upgrade, signed paired flows, read-only history, cross-portfolio API/undo, opposite-message duplicate protection, and concurrent cash checks.')
