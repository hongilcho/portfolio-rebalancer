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
