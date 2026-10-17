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
from data.repositories import trades,realized,activity,realized_openings,snapshots


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
        query("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES('old','합성 과거 잔고 ETF','QAOLD','KR','[\"acc\"]','p')")
        assert trades.execute_trade(ctx,'2026-09-28','acc','old','INIT',9,100,'KRW',1)[0]
        assert trades.execute_trade(ctx,'2026-09-29','acc','old','BUY',5,100,'KRW',1)[0]
        query("UPDATE holdings SET quantity=9 WHERE asset_id='old'")
        tables=('accounts','assets','holdings','trade_history','usd_cash_state','usd_cash_events',
                'performance_tracking','ledger_adjustments')
        def financial_state():
            return {t:query(f'SELECT row_to_json(t)::text FROM {t} t ORDER BY row_to_json(t)::text') for t in tables}
        before=financial_state()
        item=next(p for p in realized_openings.preview(ctx,'p')['candidates'] if p['asset_id']=='old')
        body=dict(request_id='legacy-opening-confirmed',positions=[{k:item[k] for k in ('account_id','asset_id','book_token')}])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:realized_openings.commit(ctx,'p',body),range(2)))
        assert results[0]==results[1] and financial_state()==before
        assert query("SELECT count(*) FROM bookkeeping_requests WHERE scope='realized-opening:p'")==[(1,)]
        assert not realized.read(ctx,'p')['warnings']
        assert realized.read(ctx,'other')['openings']==[]
        passed('legacy overlap confirmation preserves all eight financial tables; concurrent retry exactly once; scoped report')
        batch_data=snapshots.get_overview_batch_data(ctx)
        from logic.realized_opening import active
        from logic.realized_gains import calculate
        overview=calculate(batch_data['trade_history'],batch_data['holdings'],baselines=active(batch_data['realized_openings']))
        assert not overview['warnings'] and overview['summary']==realized.read(ctx,'p')['summary']
        assert financial_state()==before
        passed('overview snapshot and detailed report share the same opening without changing valuation data')
        day=__import__('datetime').datetime.now(__import__('zoneinfo').ZoneInfo('Asia/Seoul')).date().isoformat()
        new=dict(request_id='post-opening-sale',portfolio_id='p',trade_date=day,trades=[dict(account_id='acc',
            asset_id='old',trade_type='SELL',quantity=9,price=120,currency='KRW',exchange_rate=1)])
        sale=trades.execute_batch(ctx,new)
        report2=realized.read(ctx,'p');record=next(s for s in report2['sales'] if s['asset_id']=='old')
        assert record['gross_profit_krw']==180 and record['net_profit_krw'] is None
        assert not report2['warnings']
        assert trades.delete_trades(ctx,sale['trade_ids'])[0]
        assert financial_state()==before
        passed('post-opening full sale and cancellation restore exact holding, cash and original history; unknown old fees stay unknown')
        undo=dict(request_id='revoke-analysis-only',baseline_id=results[0]['positions'][0]['id'])
        realized_openings.revoke(ctx,'p',undo)
        assert financial_state()==before and realized.read(ctx,'p')['warnings']
        passed('revoking unused opening appends audit only and restores original report warning')
        from scripts import repair_realized_openings_once as repair
        from copy import deepcopy
        query('''INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd)
            VALUES('once-us','QA-US','해외ETF직투계좌','일반','p',1000000,100000),
                  ('once-gold','QA-GOLD','금현물계좌','일반','other',1000000,0)''')
        for sid,ticker,market,aid,pid,qty,extra in [
            ('once-vt','VT','US','once-us','p',63,52),('once-pdbc','PDBC','US','once-us','p',70,40),
            ('once-gold','M04020000','KR','once-gold','other',9,5)]:
            query('INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES(%s,%s,%s,%s,%s,%s)',
                (sid,'Synthetic '+ticker,ticker,market,json.dumps([aid]),pid))
            for d,k,n in [('2026-09-28','INIT',qty),('2026-09-29','BUY',extra)]:
                ok,msg=trades.execute_trade(ctx,d,aid,sid,k,n,100,'USD' if market=='US' else 'KRW',1300)
                assert ok,msg
            query('UPDATE holdings SET quantity=%s WHERE asset_id=%s',(qty,sid))
        before=financial_state();receipts=query('SELECT count(*) FROM bookkeeping_requests')
        plan=repair.prepare(ctx)
        assert financial_state()==before and query('SELECT count(*) FROM bookkeeping_requests')==receipts
        bad=deepcopy(plan);bad['positions'][0]['book_token']='0'*64
        try:repair.apply(ctx,bad)
        except ValueError:pass
        else:raise AssertionError('Stale plan must fail')
        assert financial_state()==before and query('SELECT count(*) FROM bookkeeping_requests')==receipts
        passed('one-time script selects exactly three positions; preparation is read-only; late failure rolls back all portfolio receipts')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:repair.apply(ctx,plan),range(2)))
        assert results[0]==results[1] and financial_state()==before
        assert query('SELECT count(*) FROM bookkeeping_requests')[0][0]==receipts[0][0]+2
        targets={'once-vt','once-pdbc','once-gold'}
        warnings=realized.read(ctx,'p')['warnings']+realized.read(ctx,'other')['warnings']
        assert not any(w['asset_id'] in targets for w in warnings)
        passed('concurrent one-time apply across two portfolios preserves financial rows and clears only the three target warnings')
        repair.apply(ctx,plan,rollback=True);repair.apply(ctx,plan,rollback=True)
        assert financial_state()==before
        warnings=realized.read(ctx,'p')['warnings']+realized.read(ctx,'other')['warnings']
        assert sum(w['asset_id'] in targets for w in warnings)==3
        passed('one-time rollback preserves all financial data, is idempotent and leaves original analysis audit')
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
