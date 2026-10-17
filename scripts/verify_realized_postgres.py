"""Run actual migrations/ledger SQL on a new loopback-only synthetic PG cluster.

Requires REALIZED_QA_PG_BIN pointing to already installed PostgreSQL binaries.
No production configuration, restored backups, NH, or remote DB connections.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',APP_PASSWORD='',
    APP_SESSION_SECRET='',NAMUH_APP_KEY='',NAMUH_APP_SECRET='',CMA_INTEREST_ENABLED='0',
    CMA_INTEREST_WRITES_ENABLED='0',CMA_DIAGNOSTICS_ENABLED='0',PORTFOLIO_DB_SECURITY_ENABLED='0',
    PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
import psycopg2
from psycopg2.extensions import parse_dsn
import requests
from curl_cffi import requests as curl_requests

PORT=55443
DB='realized_synthetic'
BIN=Path(os.environ['REALIZED_QA_PG_BIN']).resolve()
RUN=ROOT/'backups/local_validation'/('realized_'+uuid.uuid4().hex)
settings=dict(host='127.0.0.1',port=PORT,dbname=DB,user='realized_qa',password=secrets.token_urlsafe(32),
    connect_timeout=5,options='-c statement_timeout=15000 -c lock_timeout=10000',passfile='NUL')
connect=psycopg2.connect


def guarded(dsn=None,**kw):
    params=parse_dsn(dsn) if dsn else {};params.update(kw)
    assert params.get('host')=='127.0.0.1' and int(params.get('port',0))==PORT
    assert params.get('dbname') in (DB,'postgres')
    return connect(**params)


def blocked(*a,**kw):raise AssertionError('External IO forbidden in synthetic verification')


psycopg2.connect=guarded
requests.sessions.Session.request=blocked
curl_requests.Session.request=blocked
from data.repository_context import RepositoryContext
from data import schema
from data.repositories import trades,realized,activity


class Connection:
    def __init__(self):self.raw=guarded(**settings)
    def __getattr__(self,name):return getattr(self.raw,name)
    def __enter__(self):return self
    def __exit__(self,*a):self.raw.close()


ctx=RepositoryContext(Connection,lambda:str(uuid.uuid4()),lambda:None)


def query(sql,params=None):
    with Connection() as conn,conn.cursor() as c:
        c.execute(sql,params);result=c.fetchall() if c.description else []
        conn.commit();return result


def batch(rid,kind,qty,price,fee=0):
    return trades.execute_batch(ctx,dict(request_id=rid,portfolio_id='p',trade_date='2026-10-16',
        trades=[dict(account_id='acc',asset_id='ast',trade_type=kind,quantity=qty,price=price,
            currency='KRW',exchange_rate=1,fees_krw=fee,fees_usd=0)]))


def main():
    assert all((BIN/f).is_file() for f in ('initdb.exe','pg_ctl.exe'))
    with socket.socket() as s:assert s.connect_ex(('127.0.0.1',PORT))!=0,'QA port occupied'
    RUN.mkdir(parents=True);cluster=RUN/'cluster';pw=RUN/'password'
    pw.write_text(settings['password'],encoding='ascii')
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0);started=False;checks=[]
    report=dict(external_calls=0,production_writes=0,checks=checks,status='failed')
    def passed(name):checks.append(name);print('PASS:',name,flush=True)
    try:
        with (RUN/'init.log').open('wb') as out:
            subprocess.run([str(BIN/'initdb.exe'),'-D',str(cluster),'-U',settings['user'],
                '-A','scram-sha-256','--pwfile',str(pw),'--encoding=UTF8','--locale=C'],
                env=env,stdout=out,stderr=out,check=True,creationflags=flags)
        pw.unlink()
        subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(cluster),'-l',str(RUN/'server.log'),
            '-o',f'-h 127.0.0.1 -p {PORT}','-w','start'],env=env,check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
        started=True
        admin=guarded(**{**settings,'dbname':'postgres'})
        try:
            admin.autocommit=True
            with admin.cursor() as c:
                c.execute('CREATE DATABASE '+DB)
                for role in ('anon','authenticated','service_role'):c.execute('CREATE ROLE '+role+' NOLOGIN')
        finally:admin.close()
        schema.init_db(ctx)
        query("INSERT INTO portfolios(id,name) VALUES('p','Synthetic realized'),('other','Other')")
        query("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw) VALUES('acc','QA-ONLY','합성 ISA','ISA','p',1000000)")
        query("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES('ast','합성 채권 ETF','QA000','KR','[\"acc\"]','p')")
        query('ALTER TABLE trade_history DROP COLUMN trade_costs, DROP COLUMN accounting_basis')
        query("INSERT INTO trade_history(id,trade_date,account_id,asset_id,trade_type,quantity,price,currency,exchange_rate) VALUES('legacy','2026-01-01','acc','ast','INIT',10,100,'KRW',1)")
        old=query('SELECT * FROM trade_history')
        schema.init_db(ctx);schema.init_db(ctx)
        assert query('SELECT trade_costs,accounting_basis FROM trade_history')==[(None,None)]
        assert query('SELECT id,quantity,price FROM trade_history')==[('legacy',10.0,100.0)]
        query("DELETE FROM trade_history WHERE id='legacy'")
        passed('additive startup migration twice preserves legacy values; missing fees stay NULL')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:batch('same-receipt','BUY',10,100,20),range(2)))
        assert results[0]==results[1] and query('SELECT count(*) FROM trade_history')[0][0]==1
        assert query("SELECT deposit_krw FROM accounts WHERE id='acc'")[0][0]==998980
        passed('concurrent duplicate requests deduct principal and fees exactly once')
        sold=batch('full-sale','SELL',10,120,10)
        before=query('SELECT * FROM accounts'),query('SELECT * FROM trade_history')
        report1=realized.read(ctx,'p');assert realized.read(ctx,'p')==report1
        assert report1['sales'][0]['net_profit_krw']==170 and report1['periods'][0]['status']=='CLOSED'
        assert realized.read(ctx,'other')['sales']==[]
        assert (query('SELECT * FROM accounts'),query('SELECT * FROM trade_history'))==before
        passed('read-only repeatable snapshot reports closed realized profit; portfolio scope and cash unchanged')
        from datetime import date
        rows=activity.read_page(ctx,'p',date(2026,10,1),date(2026,10,31))
        sale=next(r for r in rows['items'] if r['kind']=='SELL')
        assert sale['detail']['trade_costs']['krw']=='10'
        passed('actual activity history SQL returns sale fee and original book evidence')
        rebuy=batch('new-period','BUY',2,200)
        assert len(realized.read(ctx,'p')['periods'])==2
        assert trades.delete_trades(ctx,rebuy['trade_ids'])[0]
        assert trades.delete_trades(ctx,sold['trade_ids'])[0]
        r=realized.read(ctx,'p');assert r['sales']==[] and r['periods'][0]['remaining_quantity']==10
        assert query("SELECT deposit_krw FROM accounts WHERE id='acc'")[0][0]==998980
        passed('reentry is separate; reversing reentry and full sale restores quantity, cash, basis and report')
        before=query('SELECT * FROM accounts'),query('SELECT * FROM trade_history')
        try:batch('fee-failure','BUY',1,100,1000000)
        except ValueError:pass
        else:raise AssertionError('fee overdraft must fail')
        assert (query('SELECT * FROM accounts'),query('SELECT * FROM trade_history'))==before
        passed('fee failure rolls back entire transaction and request receipt')
        report.update(status='passed',check_count=len(checks))
    finally:
        if pw.exists():pw.unlink()
        if started:
            stopped=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(cluster),'-m','fast','-w','stop'],
                env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            report['isolated_cluster_stopped']=stopped.returncode==0
        (ROOT/'docs/realized-postgres-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
