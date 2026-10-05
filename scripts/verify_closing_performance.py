"""Real PostgreSQL transactions on a fresh, strictly loopback synthetic DB.

Requires backups/local_validation/local_connection.json from predeploy QA.
No production config or external prices are read. Safe to run repeatedly.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sys
import threading
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
settings = json.loads((ROOT/'backups/local_validation/local_connection.json').read_text())
assert settings['host']=='127.0.0.1' and settings['port']==55437 and settings['dbname']=='postgres'
name = 'portfolio_close_'+datetime.now().strftime('%Y%m%d_%H%M%S')
admin = psycopg2.connect(**settings)
admin.autocommit = True
with admin.cursor() as c:
    c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close()
settings['dbname'] = name
original_connect = psycopg2.connect
def guarded_connect(dsn=None, *args, **kwargs):
    parsed = parse_dsn(dsn) if dsn else {}
    parsed.update(kwargs)
    assert parsed['host']=='127.0.0.1' and str(parsed['port'])=='55437'
    return original_connect(dsn, *args, **kwargs)
psycopg2.connect = guarded_connect
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0', SUPABASE_URL=make_dsn(**settings),
    NAMUH_APP_KEY='',NAMUH_APP_SECRET='',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
import requests
from curl_cffi import requests as curl_requests
def blocked(*_, **__): raise AssertionError('QA cannot call an external market')
requests.sessions.Session.request = blocked
curl_requests.Session.request = blocked

from backend.close_performance import ClosePerformance, context
from logic.close_calendar import KST
from logic.price_fetcher import calculate_deposit_price
from data import data_manager as dm
from data.repositories import performance, close_jobs
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.routers import performance as router

dm.init_db()
dm.init_db()
DAY = date(2026,10,6)
NOW = datetime(2026,10,6,16,tzinfo=KST)
performance.today = lambda: DAY
with dm.get_connection() as conn, conn.cursor() as c:
    c.execute("INSERT INTO portfolios(id,name) VALUES('other','Other QA')")
    c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd) VALUES('a','QA','QA','GENERAL','default',100,2)")
    c.execute("INSERT INTO assets(id,name,ticker,market,portfolio_id) VALUES('s','QA stock','0085P0','KR','default'),('vt','QA VT','VT','US','default')")
    c.execute("INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price) VALUES('h','a','s',3,9),('u','a','vt',1,100)")
    conn.commit()
ctx = context()
performance.capture(ctx,'default',100,{'test':True},start=True)
performance.capture(ctx,'other',100,{'test':True},start=True)

class Quotes:
    calls = []
    failed = True
    def exchange_rate(self, now):
        self.calls.append('fx')
        return {'rate':1400,'source':'QA FX','published_at':now.isoformat(),'collected_at':now.isoformat()}
    def asset(self, a, day, fx):
        self.calls.append(a['id'])
        if a['id']=='vt' and self.failed:
            raise ValueError('Synthetic failure')
        return {'id':a['id'],'ticker':a['ticker'],'source':'QA dated close',
            'price_krw':140000 if a['id']=='vt' else 10,'price_date':str(day if a['market']=='KR' else day-timedelta(days=1))}

q = Quotes()
w = ClosePerformance(ctx=ctx,prices=q,now=lambda:NOW)
assert not w.tick('default')
state = performance.read(ctx,'default')
assert state['close_jobs'][0]['state']=='retry' and state['snapshots'][0]['record_kind']=='baseline'
assert state['snapshots'][0]['value_krw']==100
with dm.get_connection() as conn, conn.cursor() as c:
    c.execute("SELECT inputs FROM performance_close_jobs WHERE portfolio_id='default'")
    inputs=c.fetchone()[0]
    assert inputs['prices']['s']['price_krw']==10 and inputs['fx']['rate']==1400
    # Changing current cash must not corrupt the frozen first attempt.
    c.execute("UPDATE accounts SET deposit_krw=200 WHERE id='a'")
    conn.commit()
q.failed = False
later = NOW+timedelta(minutes=6)
restart = ClosePerformance(ctx=ctx,prices=q,now=lambda:later,read_ledger=blocked)
assert restart.tick('default')
assert q.calls.count('fx')==1 and q.calls.count('s')==1 and q.calls.count('vt')==2
state = performance.read(ctx,'default')
assert state['snapshots'][0]['value_krw']==142930 and state['snapshots'][0]['record_kind']=='close'
assert state['close_jobs'][0]['state']=='complete'
assert not restart.tick('default')
assert not performance.capture(ctx,'default',999,{},start=False)

app = FastAPI()
app.include_router(router.router)
client = TestClient(app)
response = client.get('/api/performance/default')
assert response.status_code==200, response.text
serialized = response.json()
assert serialized['daily_reports'][0]['record_kind']=='close'
assert serialized['snapshots'][0]['fx']['rate']==1400
assert serialized['daily_reports'][0]['closes'][0]['price_date']

# Explicit correction reuses FX and prices, retains old record and invalidates
# the previous external-flow confirmation before returning a changed NAV.
performance.confirm(ctx,'default',0,DAY,142930)
correct = ClosePerformance(ctx=ctx,prices=q,now=lambda:later)
assert correct.request('default')['saved']
after = performance.read(ctx,'default')
assert after['snapshots'][0]['value_krw']==143030
assert after['tracking']['confirmed_through']<DAY
assert q.calls.count('fx')==1 and q.calls.count('s')==1 and q.calls.count('vt')==2
with dm.get_connection() as conn, conn.cursor() as c:
    c.execute("SELECT payload FROM performance_snapshots WHERE portfolio_id='default'")
    assert c.fetchone()[0]['performance_at_capture']['profit_krw']==142930
    c.execute("SELECT COUNT(*) FROM performance_snapshot_revisions WHERE portfolio_id='default'")
    assert c.fetchone()[0]==2
    c.execute("SELECT COUNT(*) FROM trade_history")
    assert c.fetchone()[0]==0
    c.execute("SELECT deposit_krw FROM accounts WHERE id='a'")
    assert c.fetchone()[0]==200

# Two workers contend for one DB job: exactly one lease can be issued.
w.schedule(NOW,'other')
barrier = threading.Barrier(2)
def concurrent_claim(_):
    barrier.wait()
    return close_jobs.claim(ctx,NOW,'other')
with ThreadPoolExecutor(max_workers=2) as pool:
    claims=list(pool.map(concurrent_claim, range(2)))
leased = next(j for j in claims if j)
assert sum(j is not None for j in claims)==1
new = close_jobs.claim(ctx,NOW+timedelta(minutes=11),'other')
assert new and new['lease_token'] != leased['lease_token']
try:
    close_jobs.progress(ctx,leased,{},NOW+timedelta(minutes=11))
    raise AssertionError('Stale worker must not publish')
except close_jobs.LeaseLost:
    pass
try:
    close_jobs.finish(ctx,leased,999,{},NOW+timedelta(minutes=11))
    raise AssertionError('Stale worker must not finish')
except close_jobs.LeaseLost:
    pass
close_jobs.fail(ctx,new,NOW+timedelta(minutes=11),'QA lease release')

# A missed day cannot use today's account cash/FX to manufacture yesterday.
past=DAY-timedelta(days=4)
close_jobs.schedule(ctx,'default',[past],DAY)
assert any(j['state']=='missed' for j in performance.read(ctx,'default')['close_jobs'])
print('PASS additive schema, partial failure/restart, frozen ledger/FX/closes, complete NAV, read serialization, same-day audited correction, confirmation invalidation, concurrent leases, stale worker rejection, missing past day, unchanged accounts/trades')
print('Synthetic local database:',name)
