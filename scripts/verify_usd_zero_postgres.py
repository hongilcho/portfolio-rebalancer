"""Real row-lock tests on a new DB in this worktree's dedicated loopback cluster.

Never reads .env, local_connection.json, production credentials, or broker data.
Start only the dedicated backups/usd_zero_pg_20261015 cluster on 127.0.0.1:55441.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn
from psycopg2.extras import RealDictCursor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
CLUSTER=(ROOT/'backups/usd_zero_pg_20261015').resolve()
EVIDENCE=ROOT/'docs/usd-zero-postgres-evidence.json'
PORT=55441
DB='usd_zero_verify_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:6]
for key in list(os.environ):
    if key.startswith('PG'):os.environ.pop(key)
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',NAMUH_APP_KEY='',NAMUH_APP_SECRET='',
    PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0',PORTFOLIO_DB_SECURITY_ENABLED='0',APP_PASSWORD='synthetic-only')
settings=dict(host='127.0.0.1',hostaddr='127.0.0.1',port=PORT,user='fx_local_qa',password='',
    connect_timeout=3,sslmode='disable',options='-c lock_timeout=10000 -c statement_timeout=20000')
original_connect=psycopg2.connect
report=dict(database=DB,host='127.0.0.1',port=PORT,cluster=str(CLUSTER),checks=[],lock_observations=[],
    synthetic_data_only=True,production_config_loaded=False,production_connections=0,external_http_calls=0)
allowed_db={'postgres'}


def guarded_connect(dsn=None,*args,**kwargs):
    params=parse_dsn(dsn) if dsn else {}
    params.update(kwargs)
    if (params.get('host')!='127.0.0.1' or params.get('hostaddr')!='127.0.0.1'
        or str(params.get('port'))!=str(PORT) or params.get('dbname') not in allowed_db
        or params.get('user')!='fx_local_qa' or params.get('service')):
        raise RuntimeError('Only the isolated loopback verification DB is allowed')
    return original_connect(*args,**params)


psycopg2.connect=guarded_connect
original_socket_connect=socket.socket.connect

def local_socket(sock,address):
    if not isinstance(address,tuple) or address[:2]!=('127.0.0.1',PORT):
        raise RuntimeError('External sockets are forbidden in this verification')
    return original_socket_connect(sock,address)


socket.socket.connect=local_socket
import requests
from curl_cffi import requests as curl_requests

def no_http(*args,**kwargs):raise RuntimeError('No external HTTP in local verification')
requests.sessions.Session.request=no_http
curl_requests.Session.request=no_http

# Check the cluster identity before making even a local CREATE DATABASE change.
with guarded_connect(**settings,dbname='postgres') as admin:
    with admin.cursor() as c:
        c.execute('SHOW data_directory');actual=Path(c.fetchone()[0]).resolve()
        if actual!=CLUSTER:raise RuntimeError('Unexpected cluster at the test port')
        c.execute('SELECT version(),host(inet_server_addr()),inet_server_port()')
        version,addr,port=c.fetchone()
        assert addr=='127.0.0.1' and port==PORT
        report['postgres_version']=version
admin=guarded_connect(**settings,dbname='postgres');admin.autocommit=True
try:
    with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DB)))
finally:admin.close()
allowed_db={DB}
os.environ['SUPABASE_URL']=make_dsn(**settings,dbname=DB)

from data import schema
from data.repository_context import RepositoryContext
from data.repositories import forex,nh_notices,trades
from backend.routers.forex import CashEvent
from backend.routers.nh_notices import Batch,Row


def connect():
    return guarded_connect(**settings,dbname=DB,application_name='fx-zero-'+threading.current_thread().name)

ctx=RepositoryContext(connect,lambda:uuid4().hex,lambda:None)
schema.init_db(ctx)


def query(statement,params=()):
    conn=connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute(statement,params);rows=[dict(r) for r in c.fetchall()] if c.description else []
        conn.commit();return rows
    finally:conn.close()


def seed(label,krw=1000000,usd=0):
    aid='qa-'+label
    query('INSERT INTO portfolios(id,name) VALUES(%s,%s)',(aid,'Synthetic '+label))
    query("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd) VALUES(%s,%s,%s,'GENERAL',%s,%s,%s)",
        (aid,aid,aid,aid,krw,usd))
    return aid


def cash(aid):return query('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s',(aid,))[0]

def state(aid):return query('SELECT * FROM usd_cash_state WHERE account_id=%s',(aid,))

def events(aid):return query('SELECT * FROM usd_cash_events WHERE account_id=%s ORDER BY sequence',(aid,))

def snapshot(aid):
    return dict(cash=cash(aid),state=state(aid),events=events(aid),
        holdings=query('SELECT * FROM holdings WHERE account_id=%s ORDER BY asset_id',(aid,)),
        trades=query('SELECT * FROM trade_history WHERE account_id=%s ORDER BY trade_sequence',(aid,)))


def manual(aid,key,usd=100,krw=140001,kind='EXCHANGE_IN',rate=0):
    return CashEvent(request_id=key,portfolio_id=aid,kind=kind,occurred_at='2026-01-02T09:00:00+09:00',
        usd_amount=usd,krw_amount=krw,rate=rate).model_dump(mode='json')


def notice(aid,key,usd=100,krw=140001):
    return Batch(request_id=key,confirmed=True,expected_cash={aid:cash(aid)},rows=[
        Row(kind='EXCHANGE_IN',account_id=aid,event_date='2026-01-02',usd_amount=usd,krw_amount=krw,
            fingerprint=hashlib.sha256(key.encode()).hexdigest())]).model_dump(mode='json')


def submit(mode,aid,body):
    try:
        result=forex.record_manual_event(ctx,aid,body) if mode=='manual' else nh_notices.commit(ctx,aid,body)
        return dict(ok=True,result=result)
    except Exception as error:return dict(ok=False,error_type=type(error).__name__,message=str(error))


def race(aid,label,actions):
    """Hold a real account row until at least one worker is observed waiting on it."""
    blocker=connect()
    with blocker.cursor() as c:c.execute('SELECT id FROM accounts WHERE id=%s FOR UPDATE',(aid,))
    blocker_pid=blocker.get_backend_pid()
    barrier=threading.Barrier(len(actions))
    def run(action):barrier.wait(timeout=5);return action()
    with ThreadPoolExecutor(max_workers=len(actions),thread_name_prefix=label) as pool:
        futures=[pool.submit(run,action) for action in actions]
        try:
            deadline=time.monotonic()+8;observed=[]
            while time.monotonic()<deadline:
                rows=query("SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid) AS blockers FROM pg_stat_activity WHERE application_name LIKE %s",('fx-zero-'+label+'%',))
                observed=[r for r in rows if r['wait_event_type']=='Lock' and blocker_pid in r['blockers']]
                if observed:break
                if any(f.done() for f in futures):raise AssertionError('Worker completed before held row lock released')
                time.sleep(.02)
            assert observed,'Did not observe the worker waiting on the real account lock'
            report['lock_observations'].append(dict(case=label,blocker_pid=blocker_pid,waiting=observed))
            assert not state(aid) and not events(aid),'Uncommitted first conversion became visible'
        finally:
            blocker.rollback();blocker.close()
        return [f.result(timeout=15) for f in futures]


def check(label,fn):
    start=time.monotonic();detail=fn()
    report['checks'].append(dict(name=label,status='PASS',seconds=round(time.monotonic()-start,3),detail=detail))
    print('PASS:',label,flush=True)


# A separately seeded established account must remain identical across all cases.
sentinel=seed('sentinel',usd=20)
assert forex.record_manual_event(ctx,sentinel,manual(sentinel,'sentinel-opening',kind='OPENING',rate=1300))['success']
assert forex.record_manual_event(ctx,sentinel,manual(sentinel,'sentinel-exchange'))['success']
sentinel_before=snapshot(sentinel)


def two_funded_conversions():
    aid=seed('funded');left=manual(aid,'funded-left');right=manual(aid,'funded-right',50,75000)
    result=race(aid,'funded',[lambda:submit('manual',aid,left),lambda:submit('manual',aid,right)])
    assert all(r['ok'] for r in result),result
    assert cash(aid)==dict(deposit_krw=784999,deposit_usd=150)
    assert len(state(aid))==1 and state(aid)[0]['cost_krw']==Decimal('215001')
    assert len(events(aid))==2 and sum(e['before_state'] is None for e in events(aid))==1
    assert all(e['after_state']['cost_krw'] for e in events(aid))
    return dict(successes=2,state_rows=1,event_rows=2,usd=150,cost_krw='215001')


def same_request(mode):
    aid=seed('retry-'+mode);body=manual(aid,'same-request-'+mode) if mode=='manual' else notice(aid,'same-request-'+mode)
    result=race(aid,'retry-'+mode,[lambda:submit(mode,aid,body),lambda:submit(mode,aid,body)])
    assert all(r['ok'] for r in result) and result[0]['result']==result[1]['result'],result
    assert cash(aid)==dict(deposit_krw=859999,deposit_usd=100)
    assert len(events(aid))==1 and len(state(aid))==1
    table='bookkeeping_requests' if mode=='manual' else 'nh_notice_batches'
    scope='scope=%s' if mode=='manual' else 'portfolio_id=%s'
    assert query('SELECT COUNT(*) AS n FROM '+table+' WHERE '+scope,('forex:'+aid if mode=='manual' else aid,))[0]['n']==1
    return dict(successful_responses=2,event_rows=1,receipt_rows=1)


def insufficient_race():
    aid=seed('insufficient',krw=200000)
    result=race(aid,'insufficient',[lambda:submit('manual',aid,manual(aid,'insufficient-left')),
        lambda:submit('manual',aid,manual(aid,'insufficient-right'))])
    assert sum(r['ok'] for r in result)==1,result
    assert any('부족' in r.get('message','') for r in result)
    assert cash(aid)==dict(deposit_krw=59999,deposit_usd=100)
    assert len(events(aid))==len(state(aid))==1
    assert query('SELECT COUNT(*) AS n FROM bookkeeping_requests WHERE scope=%s',('forex:'+aid,))[0]['n']==1
    return dict(successes=1,rejected=1,event_rows=1,receipt_rows=1)


def stale_notice_race():
    aid=seed('notice-stale');left=notice(aid,'stale-left');right=notice(aid,'stale-right',50,75000)
    result=race(aid,'notice-stale',[lambda:submit('notice',aid,left),lambda:submit('notice',aid,right)])
    assert sum(r['ok'] for r in result)==1,result
    assert any('변경' in r.get('message','') for r in result)
    assert len(events(aid))==len(state(aid))==1
    e=events(aid)[0];assert cash(aid)['deposit_usd']==float(e['usd_amount'])
    assert cash(aid)['deposit_krw']==1000000-float(e['krw_amount'])
    return dict(successes=1,stale_rejections=1,event_rows=1)


def cross_path_race():
    details=[]
    for i in range(3):
        aid=seed('mixed-'+str(i));m=manual(aid,'mixed-manual-'+str(i),50,75000);n=notice(aid,'mixed-notice-'+str(i))
        result=race(aid,'mixed-'+str(i),[lambda:submit('manual',aid,m),lambda:submit('notice',aid,n)])
        assert result[0]['ok'],result
        assert result[1]['ok'] or '변경' in result[1]['message'],result
        expected_usd=150 if result[1]['ok'] else 50
        expected_cost=215001 if result[1]['ok'] else 75000
        assert cash(aid)==dict(deposit_krw=1000000-expected_cost,deposit_usd=expected_usd)
        assert len(state(aid))==1 and state(aid)[0]['cost_krw']==expected_cost
        assert len(events(aid))==sum(r['ok'] for r in result)
        details.append(dict(manual_success=True,notice_success=result[1]['ok'],event_rows=len(events(aid))))
    return details


def concurrent_undo(mode):
    aid=seed('undo-'+mode);body=manual(aid,'undo-source-'+mode) if mode=='manual' else notice(aid,'undo-source-'+mode)
    posted=submit(mode,aid,body);assert posted['ok'],posted
    result=posted['result'];barrier=threading.Barrier(2)
    def cancel():
        barrier.wait(timeout=5)
        return forex.undo_event(ctx,aid,result['event_id']) if mode=='manual' else nh_notices.undo(ctx,aid,result['batch_id'])
    with ThreadPoolExecutor(max_workers=2) as pool:results=[f.result(timeout=15) for f in [pool.submit(cancel),pool.submit(cancel)]]
    assert (all(r[0] for r in results) if mode=='manual' else all(r['reversed'] for r in results))
    assert cash(aid)==dict(deposit_krw=1000000,deposit_usd=0) and not state(aid)
    assert len(events(aid))==1 and events(aid)[0]['reversed_at']
    retried=submit(mode,aid,body)
    assert (retried['result']['reversed'] if mode=='manual' else not retried['ok'] and '취소' in retried['message'])
    assert cash(aid)==dict(deposit_krw=1000000,deposit_usd=0) and not state(aid)
    return dict(successful_cancel_responses=2,cash_reversed_once=True,retry_reapplied=False)


def preserve_existing():
    for usd in (0,20):
        aid=seed('existing-'+str(usd),usd=usd)
        forex.record_manual_event(ctx,aid,manual(aid,'existing-opening-'+str(usd),kind='OPENING',rate=1300))
        forex.record_manual_event(ctx,aid,manual(aid,'existing-prior-'+str(usd)))
        if usd==0:
            forex.record_manual_event(ctx,aid,manual(aid,'existing-empty-again',100,140001,kind='EXCHANGE_OUT'))
            assert cash(aid)['deposit_usd']==0 and state(aid)[0]['cost_krw']==0
        before=snapshot(aid)
        result=forex.record_manual_event(ctx,aid,manual(aid,'existing-next-'+str(usd),50,75000))
        after=snapshot(aid)
        assert after['state'][0]['started_at']==before['state'][0]['started_at']
        assert after['events'][:-1]==before['events']
        assert after['state'][0]['cost_krw']==before['state'][0]['cost_krw']+75000
        assert forex.undo_event(ctx,aid,result['event_id'])[0]
        restored=snapshot(aid)
        assert restored['state']==before['state'] and restored['cash']==before['cash']
        assert restored['events'][:-1]==before['events']
    assert snapshot(sentinel)==sentinel_before
    return dict(established_accounts_preserved=2,unrelated_account_unchanged=True)


def journal_failure(mode):
    aid=seed('rollback-'+mode)
    query("CREATE OR REPLACE FUNCTION fx_qa_reject() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic first journal failure'; END $$")
    query('CREATE TRIGGER fx_qa_reject BEFORE INSERT ON usd_cash_events FOR EACH ROW EXECUTE FUNCTION fx_qa_reject()')
    before=snapshot(aid)
    try:
        body=manual(aid,'rollback-source-'+mode) if mode=='manual' else notice(aid,'rollback-source-'+mode)
        result=submit(mode,aid,body)
        assert not result['ok'] and 'synthetic first journal failure' in result['message'],result
        assert snapshot(aid)==before
        assert not query('SELECT * FROM bookkeeping_requests WHERE scope=%s',('forex:'+aid,))
        assert not query('SELECT * FROM nh_notice_batches WHERE portfolio_id=%s',(aid,))
        assert not query('SELECT * FROM nh_notice_items WHERE account_id=%s',(aid,))
    finally:
        query('DROP TRIGGER fx_qa_reject ON usd_cash_events');query('DROP FUNCTION fx_qa_reject()')
    return dict(cash_unchanged=True,state_rows=0,event_rows=0,receipts_or_batches=0)


def old_holding_preserved():
    aid=seed('holding')
    query("INSERT INTO assets(id,name,ticker,market,portfolio_id,allowed_accounts) VALUES(%s,'Synthetic US asset','QA','US',%s,%s)",(aid,aid,json.dumps([aid])))
    ok,msg=trades.execute_trade(ctx,'2026-01-01',aid,aid,'INIT',5,100,'USD',1250);assert ok,msg
    query('UPDATE holdings SET manual_dividend_override=12345 WHERE account_id=%s',(aid,))
    before=snapshot(aid)
    result=forex.record_manual_event(ctx,aid,manual(aid,'holding-exchange'))
    assert snapshot(aid)['holdings']==before['holdings'] and snapshot(aid)['trades']==before['trades']
    assert events(aid)[0]['after_state']['opening_holdings']
    assert not trades.delete_trades(ctx,[before['trades'][0]['id']])[0]
    assert forex.undo_event(ctx,aid,result['event_id'])[0]
    restored=snapshot(aid)
    assert restored['holdings']==before['holdings'] and restored['trades']==before['trades']
    assert restored['cash']==before['cash'] and not restored['state']
    return dict(holding_and_trade_unchanged=True,old_trade_deletion_blocked=True)


try:
    check('concurrent distinct first conversions serialize on a real account row',two_funded_conversions)
    for mode in ('manual','notice'):check(mode+' duplicate concurrent requests apply once',lambda mode=mode:same_request(mode))
    check('concurrent first conversions cannot overspend KRW',insufficient_race)
    check('distinct NH previews reject stale cash after lock release',stale_notice_race)
    check('manual and NH first conversions share locking and one state',cross_path_race)
    for mode in ('manual','notice'):check(mode+' concurrent first-conversion undo restores only once',lambda mode=mode:concurrent_undo(mode))
    check('existing opening and exchanges remain identical',preserve_existing)
    for mode in ('manual','notice'):check(mode+' first journal failure rolls back initialization and cash',lambda mode=mode:journal_failure(mode))
    check('first conversion preserves prior US holding costs and metadata',old_holding_preserved)
    assert snapshot(sentinel)==sentinel_before
    report['status']='PASS'
except Exception as error:
    report['status']='FAIL';report['failure']=dict(type=type(error).__name__,message=str(error))
    raise
finally:
    report['completed_at_utc']=datetime.now(timezone.utc).isoformat()
    EVIDENCE.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('Evidence:',EVIDENCE,flush=True)
print('Completed:',len(report['checks']),'checks;',len(report['lock_observations']),'real lock observations',flush=True)
