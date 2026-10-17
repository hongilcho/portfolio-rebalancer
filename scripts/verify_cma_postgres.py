"""Synthetic CMA verification on a dedicated, loopback-only PostgreSQL 17.

Never imports production configuration, restores backups, or calls NH.
Creates its own cluster/database and stops that cluster on completion.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PORT = 55439
BIN = Path(os.environ.get('CMA_QA_PG_BIN', str(ROOT/'backups/local_validation/pgsql/bin'))).resolve()
RUN = ROOT/'backups/local_validation'/('cma_pg_'+uuid.uuid4().hex)
DBNAME = 'cma_synthetic'
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0', SUPABASE_URL='',
    APP_PASSWORD='', APP_SESSION_SECRET='', NAMUH_APP_KEY='', NAMUH_APP_SECRET='',
    CMA_INTEREST_ENABLED='0', CMA_INTEREST_WRITES_ENABLED='0', CMA_DIAGNOSTICS_ENABLED='0', PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
import psycopg2
from psycopg2.extensions import parse_dsn

original_connect = psycopg2.connect
settings = dict(host='127.0.0.1',port=PORT,dbname=DBNAME,user='cma_qa_owner',
                connect_timeout=5,options='-c statement_timeout=15000 -c lock_timeout=10000')


def guarded_connect(dsn=None,**kwargs):
    parsed = parse_dsn(dsn) if dsn else {}
    parsed.update(kwargs)
    assert parsed.get('host')=='127.0.0.1' and int(parsed.get('port',0))==PORT
    assert parsed.get('dbname') in (DBNAME,'postgres')
    return original_connect(**parsed)


psycopg2.connect = guarded_connect
import requests
from curl_cffi import requests as curl_requests


def blocked(*args,**kwargs):
    raise AssertionError('External connections are forbidden in synthetic QA')


requests.sessions.Session.request = blocked
curl_requests.Session.request = blocked
from data.repository_context import RepositoryContext
from data import schema
from data.repositories import cma
from logic.cma_interest import KST, observe_balance
from logic.period_performance import report_daily
from logic import cma_policy
from logic.cma_reconciliation import reconcile
from logic.cma_interest import fingerprint

NOW = datetime(2026,10,14,12,tzinfo=KST)
checks = []


class Connection:
    def __init__(self,fail=False):
        self.raw = guarded_connect(**settings)
        self.fail = fail
    def __enter__(self): return self
    def __exit__(self,*_): self.raw.close()
    def __getattr__(self,name): return getattr(self.raw,name)
    def cursor(self,*args,**kwargs):
        cursor = self.raw.cursor(*args,**kwargs)
        if not self.fail: return cursor
        class Cursor:
            def __getattr__(self,name): return getattr(cursor,name)
            def execute(self,query,values=None):
                if 'INSERT INTO portfolio_cma.income' in query:
                    raise RuntimeError('Synthetic failure after cash update')
                return cursor.execute(query,values)
        return Cursor()


ctx = RepositoryContext(lambda:Connection(),lambda:str(uuid.uuid4()),lambda:None)


def query(statement,values=None):
    with Connection() as conn,conn.cursor() as cursor:
        cursor.execute(statement,values)
        rows = cursor.fetchall() if cursor.description else []
        conn.commit()
        return rows


def passed(name):
    checks.append(name)
    print('PASS:',name,flush=True)


def expect_failure(fn,kind=ValueError):
    try: fn()
    except kind: return
    raise AssertionError('Expected guarded rejection')


def wire(cash=4800123):
    return dict(rsp_cd='00000',rsp_msg='조회가 완료되었습니다.',
                Output_0=dict(dca=cash,nxt2_dd_dca=cash),Output_1=[])


def proposal(aid='cma',cash=4800123,now=NOW,rid=None,verified=True):
    book=cma.read_book(ctx,'p',aid)
    evidence=observe_balance(wire(cash),now)
    receipt=None
    if verified:
        opening=book['account']['deposit_krw']
        statement=dict(profile='SYNTHETIC_PG_TEST_ONLY',portfolio_id='p',account_id=aid,currency='KRW',
            complete=True,interest_posting_final=True,start_date=now.date().isoformat(),as_of=now.isoformat(),
            opening_cash_krw=str(opening),closing_cash_krw=str(cash),events=[dict(reference_hash=fingerprint(aid),
                event_date=now.date().isoformat(),kind='PAID_INTEREST',amount_krw=str(Decimal(str(cash))-Decimal(str(opening))))])
        receipt=reconcile(statement,[],pid='p',aid=aid,book_token=book['book_token'],book_cash=opening,observation=evidence)
        assert receipt['status']=='MATCHED'
    obs=cma.record_observation(ctx,'p',aid,evidence,book['book_token'],reconciliation=receipt)
    preview=cma.preview(ctx,'p',aid,obs['id'],now)
    return dict(request_id=rid or str(uuid.uuid4()),account_id=aid,confirmed_movements=True,
        **{k:preview[k] for k in ('observation_id','book_token','interest_krw')})


def race(fn,count=2):
    gate=threading.Barrier(count)
    def invoke(i):
        gate.wait()
        try: return ('ok',fn(i))
        except Exception as exc: return ('error',type(exc).__name__)
    with ThreadPoolExecutor(max_workers=count) as executor:
        return list(executor.map(invoke,range(count)))


def main():
    assert all((BIN/name).is_file() for name in ('initdb.exe','pg_ctl.exe')), 'Set CMA_QA_PG_BIN to local PostgreSQL binaries'
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1',PORT))!=0,'Dedicated QA port is already occupied'
    RUN.mkdir(parents=True)
    cluster=RUN/'cluster'
    log=RUN/'server.log'
    password=secrets.token_urlsafe(32)
    settings['password']=password
    pw=RUN/'init_password'
    pw.write_text(password,encoding='ascii')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    started=False
    report=dict(external_calls=0,production_ledger_writes=0,deployments=0,
                database='dedicated synthetic PostgreSQL 17.6',host='127.0.0.1',port=PORT)
    try:
        with (RUN/'init.log').open('wb') as output:
            subprocess.run([str(BIN/'initdb.exe'),'-D',str(cluster),'-U',settings['user'],
                '-A','scram-sha-256','--pwfile',str(pw),'--encoding=UTF8','--locale=C'],
                env=env,stdout=output,stderr=output,check=True,creationflags=flags)
        pw.unlink()
        subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(cluster),'-l',str(log),'-o',
            f'-h 127.0.0.1 -p {PORT}','-w','start'],env=env,check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
        started=True
        admin=guarded_connect(**{**settings,'dbname':'postgres'})
        try:
            admin.autocommit=True
            with admin.cursor() as cursor:
                cursor.execute('CREATE DATABASE cma_synthetic')
                for role in ('anon','authenticated','service_role'):
                    cursor.execute('CREATE ROLE '+role+' NOLOGIN')
        finally: admin.close()
        schema.init_db(ctx)
        assert query("SELECT to_regnamespace('portfolio_cma')")[0][0] is None
        passed('default-off startup creates no CMA schema')
        os.environ['CMA_INTEREST_ENABLED']='1'
        schema.init_db(ctx)
        schema.init_db(ctx)
        passed('actual application DDL initializes twice without data loss')
        assert query("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='portfolio_cma' AND c.relkind='r' AND c.relrowsecurity")[0][0]==5
        for role in ('anon','authenticated','service_role'):
            assert not query("SELECT has_schema_privilege(%s,'portfolio_cma','USAGE')",(role,))[0][0]
            assert not query("SELECT has_table_privilege(%s,'portfolio_cma.income','SELECT,INSERT,UPDATE,DELETE')",(role,))[0][0]
            assert not query("SELECT has_table_privilege(%s,'portfolio_cma.openings','SELECT,INSERT,UPDATE,DELETE')",(role,))[0][0]
            assert not query("SELECT has_sequence_privilege(%s,'portfolio_cma.income_sequence_seq','USAGE,SELECT,UPDATE')",(role,))[0][0]
        passed('five tables use RLS; Data API roles cannot access schema, income, opening journal or sequence')
        query("INSERT INTO portfolios(id,name) VALUES('p','Synthetic CMA'),('other','Other synthetic portfolio')")
        for aid in ('cma','race','rollback','auto','stale','proofless','initial','catchup'):
            query("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw) VALUES(%s,%s,%s,'CMA','p',4800000)",(aid,'QA-'+aid,aid))
        query("INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload) VALUES('p','2026-10-13',5000000,'{}')")
        query("INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,amount_krw,currency,native_amount,exchange_rate) VALUES('withdrawal','p','cma','recorded-withdrawal','2026-10-14',-200000,'KRW',200000,1)")
        original_flow=query('SELECT * FROM performance_flows')
        expect_failure(lambda:cma.commit(ctx,'p',{},NOW))
        expect_failure(lambda:cma.undo(ctx,'p','cma','not-created'))
        assert query('SELECT count(*) FROM portfolio_cma.income')[0][0]==0
        passed('read-only global mode blocks income and undo before any ledger writes')
        os.environ['CMA_INTEREST_WRITES_ENABLED']='1'  # Synthetic database only.
        assert not cma_policy.VALIDATED_STATEMENT_PROFILES
        # Only this isolated QA process trusts this synthetic profile.
        cma_policy.VALIDATED_STATEMENT_PROFILES=frozenset({'SYNTHETIC_PG_TEST_ONLY'})
        reference=wire(0);reference['Output_0']['drn_pbl_amt']='4800123'
        book=cma.read_book(ctx,'p','stale')
        obs=cma.record_observation(ctx,'p','stale',observe_balance(reference,NOW.replace(hour=18)),book['book_token'])
        assert query('SELECT evidence->>\'withdrawable_krw\' FROM portfolio_cma.observations WHERE id=%s',(obs['id'],))[0][0]=='4800123'
        expect_failure(lambda:cma.preview(ctx,'p','stale',obs['id'],NOW.replace(hour=18)))
        assert query("SELECT deposit_krw FROM accounts WHERE id='stale'")[0][0]==4800000
        passed('zero cash retains withdrawal reference in JSONB without granting an income preview or cash write')
        req=proposal()
        results=race(lambda _:cma.commit(ctx,'p',req,NOW))
        assert all(state=='ok' for state,_ in results),results
        assert results[0][1]==results[1][1]
        assert query("SELECT deposit_krw FROM accounts WHERE id='cma'")[0][0]==4800123
        assert query("SELECT count(*) FROM portfolio_cma.income WHERE account_id='cma'")[0][0]==1
        passed('simultaneous identical requests return one durable income receipt and one cash increase')
        assert cma.commit(ctx,'p',req,NOW+timedelta(days=1))==results[0][1]
        expect_failure(lambda:cma.commit(ctx,'p',{**req,'interest_krw':'124'},NOW))
        passed('next-day lost-response retry recovers original receipt; changed payload is rejected')
        assert query('SELECT * FROM performance_flows')==original_flow
        daily=report_daily({'baseline_date':date(2026,10,13),'baseline_value':5000000},
            [{'snapshot_date':date(2026,10,14),'value_krw':4800123}],
            [{'event_date':date(2026,10,14),'amount_krw':-200000,'voided':False}])
        assert daily[0]['profit']==123 and daily[0]['return_pct']>0
        assert query('SELECT count(*) FROM holdings')[0][0]==query('SELECT count(*) FROM trade_history')[0][0]==0
        passed('already-booked 200,000 withdrawal stays intact; interest produces 123 profit without trade or flow')
        reqs=[proposal('race',rid='separate-'+str(i)) for i in range(2)]
        results=race(lambda i:cma.commit(ctx,'p',reqs[i],NOW))
        assert sum(state=='ok' for state,_ in results)==1,results
        assert query("SELECT deposit_krw FROM accounts WHERE id='race'")[0][0]==4800123
        passed('different concurrent requests cannot post the same account/day twice')
        req=proposal('rollback',now=NOW.replace(hour=21))
        failing=RepositoryContext(lambda:Connection(fail=True),ctx.new_id,ctx.invalidate)
        expect_failure(lambda:cma.commit(failing,'p',req,NOW.replace(hour=21)),RuntimeError)
        assert query("SELECT deposit_krw FROM accounts WHERE id='rollback'")[0][0]==4800000
        assert query('SELECT count(*) FROM bookkeeping_requests WHERE request_id=%s',(req['request_id'],))[0][0]==0
        assert query("SELECT count(*) FROM portfolio_cma.income WHERE account_id='rollback'")[0][0]==0
        passed('injected failure rolls back cash, income and request receipt together')
        book=cma.read_book(ctx,'p','stale')
        query("UPDATE accounts SET deposit_krw=deposit_krw+1 WHERE id='stale'")
        expect_failure(lambda:cma.record_observation(ctx,'p','stale',observe_balance(wire(),NOW),book['book_token']))
        expect_failure(lambda:cma.read_book(ctx,'other','cma'))
        passed('changed book during NH read and wrong portfolio scope are rejected')
        claims=race(lambda _:cma.claim_check(ctx,'cma',date(2026,10,14),0),count=8)
        assert all(state=='ok' for state,_ in claims),claims
        assert sum(bool(value) for _,value in claims)==1
        assert not cma.claim_check(ctx,'cma',date(2026,10,14),0)
        passed('eight concurrent workers consume one durable slot; restart cannot repeat it')
        assert cma.read(ctx,'p')['checks'][0]['account_id']=='cma'
        passed('daily check status keeps account identity for scoped missing/failure alerts')
        policy=dict(enabled=True,auto_apply=True,max_auto_interest='100',movements_confirmed=True)
        cma_policy.VALIDATED_STATEMENT_PROFILES=frozenset()
        expect_failure(lambda:cma.configure(ctx,'p','auto',policy))
        passed('unvalidated live statement profiles cannot enable automatic income')
        # A synthetic-only registry exists solely inside this QA process.
        cma_policy.VALIDATED_STATEMENT_PROFILES=frozenset({'SYNTHETIC_PG_TEST_ONLY'})
        cma.configure(ctx,'p','proofless',{**policy,'max_auto_interest':'200'})
        proposal('proofless',now=NOW-timedelta(minutes=3))
        missing=proposal('proofless',verified=False)
        expect_failure(lambda:cma.commit(ctx,'p',{**missing,'automatic':True},NOW))
        assert query("SELECT deposit_krw FROM accounts WHERE id='proofless'")[0][0]==4800000
        passed('stable cash, user opt-in and cap cannot replace bank reconciliation evidence')
        proposal('auto',now=NOW-timedelta(minutes=3),verified=True)
        req=proposal('auto',verified=True)
        cma.configure(ctx,'p','auto',policy)
        expect_failure(lambda:cma.commit(ctx,'p',{**req,'automatic':True},NOW))
        cma.configure(ctx,'p','auto',{**policy,'max_auto_interest':'200'})
        applied=cma.commit(ctx,'p',{**req,'automatic':True},NOW)
        cma.undo(ctx,'p','auto',applied['income_id'])
        assert query("SELECT deposit_krw FROM accounts WHERE id='auto'")[0][0]==4800000
        assert not query("SELECT auto_apply FROM portfolio_cma.settings WHERE account_id='auto'")[0][0]
        assert cma.undo(ctx,'p','auto',applied['income_id'])['reversed']
        passed('automatic cap rechecked under locks; stable observation posts once; undo disables auto and is idempotent')
        book=cma.read_book(ctx,'p','initial')
        evidence=observe_balance(wire(),NOW)
        initial_statement=dict(profile='SYNTHETIC_PG_TEST_ONLY',portfolio_id='p',account_id='initial',currency='KRW',
            complete=True,interest_posting_final=True,start_date=NOW.date().isoformat(),as_of=NOW.isoformat(),
            opening_cash_krw='4800100',closing_cash_krw='4800123',events=[dict(reference_hash=fingerprint('initial-paid'),
                event_date=NOW.date().isoformat(),kind='PAID_INTEREST',amount_krw='23')])
        proof=reconcile(initial_statement,[],pid='p',aid='initial',book_token=book['book_token'],
            book_cash=4800000,observation=evidence)
        obs=cma.record_observation(ctx,'p','initial',evidence,book['book_token'],reconciliation=proof)
        initial_req=dict(request_id='initial-review',account_id='initial',observation_id=obs['id'],book_token=book['book_token'],
            initial_interest_krw='100',confirmed_initial_interest=True,reason='Synthetic verified accumulated interest, no external flows.')
        results=race(lambda _:cma.initialize_interest(ctx,'p',initial_req,NOW))
        assert all(state=='ok' for state,_ in results) and results[0][1]==results[1][1],results
        assert query("SELECT deposit_krw FROM accounts WHERE id='initial'")[0][0]==4800100
        assert query("SELECT count(*) FROM portfolio_cma.openings WHERE account_id='initial'")[0][0]==1
        assert query("SELECT count(*) FROM portfolio_cma.income WHERE account_id='initial'")[0][0]==0
        assert query("SELECT details->'historical_payment_dates' FROM portfolio_cma.openings WHERE account_id='initial'")[0][0] is None
        passed('simultaneous opening requests post prior interest once, without daily income or fabricated payment dates')
        expect_failure(lambda:cma.commit(ctx,'p',dict(request_id='initial-stale',account_id='initial',observation_id=obs['id'],
            book_token=book['book_token'],interest_krw='123',confirmed_movements=True),NOW))
        daily=cma.commit(ctx,'p',proposal('initial',verified=True),NOW)
        assert Decimal(daily['interest_krw'])==23
        initial_id=results[0][1]['opening_id']
        expect_failure(lambda:cma.undo_initial_interest(ctx,'p','initial',initial_id))
        cma.undo(ctx,'p','initial',daily['income_id'])
        cma.undo_initial_interest(ctx,'p','initial',initial_id)
        assert query("SELECT deposit_krw FROM accounts WHERE id='initial'")[0][0]==4800000
        passed('opening invalidates old observations; fresh daily receipt posts only today; reversal honors later writes')
        book=cma.read_book(ctx,'p','catchup');evidence=observe_balance(wire(4800200),NOW)
        dates=[(NOW-timedelta(days=1)).date().isoformat(),NOW.date().isoformat()]
        catchup_statement=dict(profile='SYNTHETIC_PG_TEST_ONLY',portfolio_id='p',account_id='catchup',currency='KRW',
            complete=True,interest_posting_final=True,start_date=dates[0],as_of=NOW.isoformat(),opening_cash_krw='4800000',
            closing_cash_krw='4800200',events=[dict(reference_hash=fingerprint(d),event_date=d,kind='PAID_INTEREST',amount_krw='100') for d in dates])
        proof=reconcile(catchup_statement,[],pid='p',aid='catchup',book_token=book['book_token'],book_cash=4800000,observation=evidence)
        cma.record_observation(ctx,'p','catchup',observe_balance(wire(4800200),NOW-timedelta(minutes=3)),book['book_token'])
        obs=cma.record_observation(ctx,'p','catchup',evidence,book['book_token'],reconciliation=proof)
        cma.configure(ctx,'p','catchup',{**policy,'max_auto_interest':'150'})
        req=dict(request_id='catchup-request',account_id='catchup',observation_id=obs['id'],book_token=book['book_token'],
            interest_krw='200',confirmed_movements=True,automatic=True)
        posted=cma.commit(ctx,'p',req,NOW)
        assert len(posted['income_ids'])==2
        assert [str(row[0]) for row in query("SELECT event_date FROM portfolio_cma.income WHERE account_id='catchup' ORDER BY event_date")]==dates
        assert cma.commit(ctx,'p',req,NOW+timedelta(days=1))==posted
        cma.undo(ctx,'p','catchup',posted['income_ids'][0])
        assert query("SELECT deposit_krw FROM accounts WHERE id='catchup'")[0][0]==4800000
        passed('missed dates post atomically with per-payment-day cap; exact retry and whole-batch reversal preserve cash')
        first=query("SELECT id FROM portfolio_cma.income WHERE account_id='cma'")[0][0]
        query("UPDATE accounts SET deposit_krw=deposit_krw-1 WHERE id='cma'")
        expect_failure(lambda:cma.undo(ctx,'p','cma',first))
        passed('undo cannot overwrite a later cash movement')
        # Verify owner guard using a transactional alternate schema owner.
        conn=Connection()
        try:
            cursor=conn.cursor()
            cursor.execute('CREATE ROLE cma_untrusted NOLOGIN')
            cursor.execute('ALTER SCHEMA portfolio_cma OWNER TO cma_untrusted')
            from data.cma_schema import initialize
            expect_failure(lambda:initialize(cursor),psycopg2.Error)
            conn.rollback()
        finally: conn.close()
        passed('unexpected schema owner is rejected before reuse')
        report.update(status='passed',checks=checks,check_count=len(checks))
    except Exception as exc:
        report.update(status='failed',checks=checks,error_type=type(exc).__name__)
        raise
    finally:
        if pw.exists(): pw.unlink()
        if started:
            stopped=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(cluster),'-m','fast','-w','stop'],
                env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            report['isolated_cluster_stopped']=stopped.returncode==0
        report['synthetic_files_location']=str(RUN.relative_to(ROOT))
        (ROOT/'docs/cma-postgres-evidence.json').write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__': main()
