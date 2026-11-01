"""Offline synthetic verification. Only this worktree's new loopback cluster.

No .env, production dump, broker credentials or remote connection is permitted.
Run explicitly: python scripts/verify_maintenance_refactor.py
"""
import ast
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
import types

ROOT=Path(__file__).resolve().parents[1]
BASE='13915706cbbbe3a0d2f686b4251801a724425e69'
CLUSTER=(ROOT/'backups/maintenance-refactor/cluster').resolve()
EVIDENCE=ROOT/'backups/maintenance-refactor'
PORT=55473
DB='refactor_reads'
sys.path.insert(0,str(ROOT))


def isolate():
    for key in list(os.environ):
        if key.startswith(('PG','AWS_','NAMUH_','SUPABASE_')):os.environ.pop(key)
    os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',NAMUH_APP_KEY='',NAMUH_APP_SECRET='',
        PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0',CMA_INTEREST_ENABLED='0',CMA_INTEREST_WRITES_ENABLED='0',
        CMA_DIAGNOSTICS_ENABLED='0',PORTFOLIO_DB_SECURITY_ENABLED='0',APP_PASSWORD='synthetic-only',
        APP_SESSION_SECRET='synthetic-refactor-session-only-32-characters')
    import psycopg2
    from psycopg2.extensions import parse_dsn
    original=psycopg2.connect
    def guarded(dsn=None,**kwargs):
        settings=parse_dsn(dsn) if dsn else dict(kwargs)
        if settings.get('host')!='127.0.0.1' or int(settings.get('port',0))!=PORT:
            raise RuntimeError('Only the dedicated loopback DB is permitted')
        if settings.get('dbname') not in ('postgres','refactor_reads','refactor_before','refactor_after'):
            raise RuntimeError('Unexpected synthetic database name')
        return original(dsn,**kwargs) if dsn else original(**kwargs)
    psycopg2.connect=guarded
    original_socket=socket.socket.connect
    def local_socket(sock,address):
        if not isinstance(address,tuple) or address[:2]!=('127.0.0.1',PORT):
            raise RuntimeError('External sockets forbidden')
        return original_socket(sock,address)
    socket.socket.connect=local_socket
    import requests
    from curl_cffi import requests as curl_requests
    def blocked(*args,**kwargs):raise RuntimeError('HTTP forbidden in synthetic verification')
    requests.sessions.Session.request=blocked;curl_requests.Session.request=blocked
    return psycopg2


def baseline_module(path):
    code=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-C',str(ROOT),'show',BASE+':'+path],text=True,encoding='utf-8')
    module=types.ModuleType('refactor_baseline_'+Path(path).stem)
    module.__file__=str(ROOT/path);sys.modules[module.__name__]=module
    exec(compile(code,module.__file__,'exec'),module.__dict__)
    return module


class Connection:
    def __init__(self,raw,queries):self.raw=raw;self.queries=queries
    def __getattr__(self,name):return getattr(self.raw,name)
    def cursor(self,*args,**kwargs):return Cursor(self.raw.cursor(*args,**kwargs),self.queries)
    def __enter__(self):return self
    def __exit__(self,*args):self.raw.rollback();self.raw.close()


class Cursor:
    def __init__(self,raw,queries):self.raw=raw;self.queries=queries
    def __getattr__(self,name):return getattr(self.raw,name)
    def execute(self,query,params=None):self.queries.append((query,params));return self.raw.execute(query,params)
    def __enter__(self):return self
    def __exit__(self,*args):self.raw.close()


def context(pg,name=DB,queries=None):
    from data.repository_context import RepositoryContext
    sequence=itertools.count(1);queries=[] if queries is None else queries
    def connect():return Connection(pg.connect(host='127.0.0.1',port=PORT,user='refactor_test',dbname=name),queries)
    return RepositoryContext(connect,lambda:f'synthetic-{next(sequence):08}',lambda:None,lambda:1400)


def prepare(pg,name):
    settings=dict(host='127.0.0.1',port=PORT,user='refactor_test')
    admin=pg.connect(**settings,dbname='postgres');admin.autocommit=True
    with admin.cursor() as c:
        c.execute('SHOW data_directory')
        if Path(c.fetchone()[0]).resolve()!=CLUSTER:raise RuntimeError('Wrong cluster identity')
        c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,))
        exists=c.fetchone() is not None
        from psycopg2 import sql
        if exists:
            if '--reset' not in sys.argv:raise RuntimeError('Synthetic DB exists; --reset is required for this dedicated QA cluster')
            c.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    admin.close()
    from data import schema
    ctx=context(pg,name)
    with ctx.connect() as conn:
        schema._do_init_db_schema(ctx,conn,conn.cursor())
    return ctx


def fingerprint(ctx):
    from psycopg2 import sql
    rows={}
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname='public' OR schemaname LIKE 'portfolio_%%' ORDER BY 1,2")
        for schema,table in c.fetchall():
            c.execute(sql.SQL('SELECT row_to_json(t) FROM {}.{} t').format(sql.Identifier(schema),sql.Identifier(table)))
            values=sorted(json.dumps(r[0],sort_keys=True,default=str) for r in c.fetchall())
            rows[schema+'.'+table]=hashlib.sha256('\n'.join(values).encode()).hexdigest()
    return rows


def normalized(raw):
    raw=deepcopy(raw)
    for cache in raw.get('dividend_cache',{}).values():cache.pop('age_seconds',None)
    for key in ('accounts','assets','holdings','trade_history','crypto_holdings'):
        if key in raw:raw[key]=sorted(raw[key],key=lambda r:str(r.get('id','')))
    return raw


def seed_reads(ctx):
    from psycopg2.extras import Json,execute_values
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO portfolios(id,name) VALUES('other','Other synthetic')")
        accounts=[];assets=[];holdings=[];trades=[]
        for pid,count in [('default',12),('other',240)]:
            for i in range(count):
                aid=f'{pid}-a{i}';sid=f'{pid}-s{i}';ticker=f'QA{pid}{i}'
                accounts.append((aid,'QA-'+aid,aid,'GENERAL',100000.0,0.0,pid))
                assets.append((sid,sid,ticker,'KR',100/count,json.dumps([aid]),pid))
                holdings.append((f'h-{aid}',aid,sid,10.0,100.0,100.0))
                for j in range(30):trades.append((f'{aid}-t{j}',f'2026-01-{j+1:02}',aid,sid,'BUY',1,100,'KRW',1,0,0))
        execute_values(c.raw,'INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,deposit_usd,portfolio_id) VALUES %s',accounts)
        execute_values(c.raw,'INSERT INTO assets(id,name,ticker,market,target_weight,allowed_accounts,portfolio_id) VALUES %s',assets)
        execute_values(c.raw,'INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,original_avg_price) VALUES %s',holdings)
        execute_values(c.raw,'INSERT INTO trade_history(id,trade_date,account_id,asset_id,trade_type,quantity,price,currency,exchange_rate,cash_delta_krw,cash_delta_usd) VALUES %s',trades)
        c.execute("INSERT INTO market_cache(key,data) VALUES('div_KR_QADEFAULT0',%s)",(Json([]),))
        c.execute("INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload) VALUES('default','2026-10-05',100000,%s)",(Json({}),))
        metrics=dict(status='COMPLETE',profit_krw=2000,cost_krw=10000,value_krw=12000,return_pct=20,version=1)
        for i in range(16):
            day=date(2026,10,5)+timedelta(days=i)
            c.execute("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES('default',%s,12000,%s,'close')",(day,Json({'holding_metrics':metrics})))
        conn.commit()


def read_checks(ctx,report):
    from data.repositories import snapshots,holding_history
    from backend.valuation_service import evaluate_portfolio
    from logic.portfolio_valuation import index_valuation_inputs
    from logic.dividend_calculator import calculate_holding_dividends
    before=baseline_module('data/repositories/snapshots.py')
    old_history=baseline_module('data/repositories/holding_history.py')
    protected=fingerprint(ctx)
    old=before.get_overview_batch_data(ctx)
    all_new=snapshots.get_overview_batch_data(ctx)
    assert normalized(old)==normalized(all_new),'Default overview contract changed'
    selected=snapshots.get_overview_batch_data(ctx,'default')
    for key,field in [('accounts','portfolio_id'),('assets','portfolio_id')]:
        assert selected[key]==[r for r in old[key] if r[field]=='default']
    ids={r['id'] for r in selected['accounts']}
    assert selected['trade_history']==[r for r in old['trade_history'] if r['account_id'] in ids]
    assert len(selected['holdings'])==12 and selected['crypto_holdings']==[]
    assert selected['portfolios']==old['portfolios']
    # All pre-period acquisitions remain available.
    assert len(selected['trade_history'])==360 and max(r['trade_date'] for r in selected['trade_history'])<'2026-10-05'
    def evaluate(batch):
        accounts=[a for a in batch['accounts'] if a['portfolio_id']=='default']
        assets=[a for a in batch['assets'] if a['portfolio_id']=='default']
        prices={a['id']:120 for a in assets}
        return evaluate_portfolio(accounts,assets,index_valuation_inputs(batch['holdings'],batch['trade_history'],[]),prices,1400,
            calculate_adjustment=lambda h,a,rate,account_type='',trades=None:calculate_holding_dividends(h,a,rate,account_type,trades,[]))
    assert evaluate(old)==evaluate(selected),'Scoped financial result changed'
    old_queries=[];new_queries=[]
    result_before=old_history.read(context(pg,queries=old_queries),'default',False)
    result_after=holding_history.read(context(pg,queries=new_queries),'default',False)
    assert result_before==result_after,'Frozen history changed'
    assert len(new_queries)<len(old_queries)
    def timed(fn):
        times=[]
        for _ in range(5):
            started=time.perf_counter();fn();times.append((time.perf_counter()-started)*1000)
        return round(statistics.median(times),3)
    report['reads']={'all_trades':len(old['trade_history']),'scoped_trades':len(selected['trade_history']),
        'all_payload_bytes':len(json.dumps(old,default=str).encode()),'scoped_payload_bytes':len(json.dumps(selected,default=str).encode()),
        'old_median_ms':timed(lambda:before.get_overview_batch_data(ctx)),
        'scoped_median_ms':timed(lambda:snapshots.get_overview_batch_data(ctx,'default')),
        'frozen_history_old_queries':len(old_queries),'frozen_history_new_queries':len(new_queries)}
    assert fingerprint(ctx)==protected,'Reads mutated synthetic financial records'
    report['reads']['protected_tables_unchanged']=True


def legacy_read_checks(ctx, report):
    from data.repositories import snapshots, holding_history
    from psycopg2.extras import Json
    batch = snapshots.get_overview_batch_data(ctx, 'default')
    account = next(a for a in batch['accounts'] if a['id']=='default-a0')
    asset = next(a for a in batch['assets'] if a['id']=='default-s0')
    holding = deepcopy(next(h for h in batch['holdings'] if h['account_id']==account['id']))
    holding.update(quantity=30, avg_price=100, original_avg_price=100, first_buy_date='2026-01-01')
    payload = dict(ledger=dict(accounts=[account], assets=[asset], holdings=[holding]),
                   prices={asset['id']:dict(id=asset['id'],price_krw=120)}, fx={'rate':1400})
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute("UPDATE market_cache SET data=%s WHERE key='div_KR_QADEFAULT0'",(Json([{'date':'2026-09-01','amount':1}]),))
        c.execute("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES('default','2026-10-21',12000,%s,'close')",(Json(payload),))
        conn.commit()
    protected = fingerprint(ctx)
    before = baseline_module('data/repositories/holding_history.py').read(ctx,'default',False)
    queries=[]
    after = holding_history.read(context(pg,queries=queries),'default',False)
    assert before == after, 'Legacy scoped reconstruction changed'
    row = next(r for r in after['rows'] if r['date']=='2026-10-21')
    assert row['status']=='COMPLETE' and row['source']=='RECONSTRUCTED'
    assert row['dividend_krw']>0, 'Pre-period trade/dividend inputs were lost'
    cache_params=next(params for query,params in queries if 'FROM market_cache WHERE key=ANY' in query)
    assert cache_params==(['div_KR_QADEFAULT0'],), cache_params
    assert fingerprint(ctx)==protected
    report['legacy_history'] = dict(full_result_equal=True,pre_period_dividends_preserved=True,
                                   scoped_cache_keys=True,protected_tables_unchanged=True)


def main():
    global pg
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    pg=isolate()
    ctx=prepare(pg,DB);seed_reads(ctx)
    report={'baseline':BASE,'environment':'fresh synthetic PostgreSQL, loopback only','port':PORT,'production_access':False}
    read_checks(ctx,report)
    legacy_read_checks(ctx,report)
    (EVIDENCE/'postgres-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()
