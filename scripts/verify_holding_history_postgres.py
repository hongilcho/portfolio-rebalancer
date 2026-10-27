"""Disposable loopback PostgreSQL: history/read purity/privacy/duplicate capture."""
import os,sys,json,subprocess,socket,uuid,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['REALIZED_QA_PG_BIN']=os.environ['HISTORY_QA_PG_BIN']
from scripts import verify_realized_postgres as qa
from data.repositories import holding_history as repo
from data.analytics_schema import initialize
from psycopg2.extras import Json
from datetime import date,datetime
from logic.close_calendar import KST
qa.PORT=55447;qa.DB='holding_history_qa';qa.settings.update(port=qa.PORT,dbname=qa.DB,user='history_qa')
qa.RUN=ROOT/'backups/local_validation'/('holding_history_'+uuid.uuid4().hex)
q=qa.query;ctx=qa.ctx
def main():
    with socket.socket() as s:assert s.connect_ex(('127.0.0.1',qa.PORT))!=0
    qa.RUN.mkdir(parents=True);cluster=qa.RUN/'cluster';pw=qa.RUN/'password';pw.write_text(qa.settings['password'])
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')};flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    report={'status':'failed','production_connections':0,'external_calls':0,'checks':[]};started=False
    def passed(name):report['checks'].append(name);print('PASS:',name,flush=True)
    def unchanged():return [q('SELECT row_to_json(t) FROM '+table+' t ORDER BY row_to_json(t)::text') for table in ['accounts','assets','holdings','trade_history','bookkeeping_requests','performance_snapshots','performance_tracking','performance_flows']]
    try:
        with (qa.RUN/'init.log').open('wb') as log:
            subprocess.run([str(qa.BIN/'initdb.exe'),'-D',str(cluster),'-U',qa.settings['user'],'-A','scram-sha-256','--pwfile',str(pw),'--encoding=UTF8','--locale=C'],env=env,stdout=log,stderr=log,creationflags=flags,check=True)
        pw.unlink()
        subprocess.run([str(qa.BIN/'pg_ctl.exe'),'-D',str(cluster),'-l',str(qa.RUN/'server.log'),'-o',f'-h 127.0.0.1 -p {qa.PORT}','-w','start'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,check=True);started=True
        admin=qa.guarded(**{**qa.settings,'dbname':'postgres'});admin.autocommit=True
        with admin.cursor() as c:
            c.execute('CREATE DATABASE '+qa.DB)
            for role in ['anon','authenticated','service_role']:c.execute('CREATE ROLE '+role+' NOLOGIN'+(' BYPASSRLS' if role=='service_role' else ''))
        admin.close();qa.schema.init_db(ctx)
        q("INSERT INTO portfolios(id,name) VALUES('q','합성 일반')")
        q("UPDATE portfolios SET name='합성 장기' WHERE id='default'")
        assert q('SELECT count(*) FROM portfolios')==[(2,)]
        q("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw) VALUES('a','QA','합성','ISA','default',10000)")
        def metric(cost,profit):return dict(version=1,status='COMPLETE',source='RECORDED',value_krw=cost+profit,cost_krw=cost,profit_krw=profit,return_pct=profit/cost*100)
        for pid,cost,profit in [('default',100,10),('q',900,0)]:
            q("INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload,close_started_on) VALUES(%s,'2026-10-05',%s,'{}','2026-10-06')",(pid,cost))
            q("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES(%s,'2026-10-27',%s,%s,'close')",(pid,cost+profit,Json({'holding_metrics':metric(cost,profit)})))
        before=unchanged();qa.schema.init_db(ctx);qa.schema.init_db(ctx);assert unchanged()==before
        passed('repeated additive migration preserves every original financial row and saved NAV')
        payload={'metrics':metric(100,-10),'holdings':[],'prices':{}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:repo.capture_crypto(ctx,date(2026,10,27),datetime(2026,10,27,16,tzinfo=KST),payload),range(2)))
        assert sum(results)==1 and repo.crypto_exists(ctx,date(2026,10,27))
        assert q('SELECT count(*) FROM portfolio_analytics.crypto_snapshots')==[(1,)]
        passed('concurrent crypto capture inserts exactly once and never overwrites a prior observation')
        for _ in range(2):
            all_assets=repo.read(ctx,'all',True);assert all_assets['rows'][0]['cost_krw']==1100 and all_assets['rows'][0]['profit_krw']==0
            without=repo.read(ctx,'all',False);assert without['rows'][0]['return_pct']==1
            assert repo.read(ctx,'default')['rows'][0]['profit_krw']==10
        assert unchanged()==before
        passed('repeatable read combines weighted costs and crypto once without ledger or NAV writes')
        from psycopg2.pool import ThreadedConnectionPool
        from data.connection import get_connection
        from data.repository_context import RepositoryContext
        pool=ThreadedConnectionPool(1,2,**qa.settings)
        pooled=RepositoryContext(lambda:get_connection(lambda:pool),lambda:'synthetic',lambda:None)
        try:
            assert repo.read(pooled,'default')['rows'][0]['profit_krw']==10
            with pooled.connect() as conn,conn.cursor() as c:
                c.execute('SHOW transaction_read_only');assert c.fetchone()[0]=='off'
                c.execute("UPDATE accounts SET deposit_krw=deposit_krw WHERE id='a'");conn.rollback()
        finally:pool.closeall()
        passed('real pooled wrapper reads safely and returns a writable connection without session leakage')
        for role in ['anon','authenticated','service_role']:
            conn=ctx.connect()
            try:
                with conn.cursor() as c:
                    c.execute('SET LOCAL ROLE '+role)
                    try:c.execute('SELECT * FROM portfolio_analytics.crypto_snapshots')
                    except qa.psycopg2.errors.InsufficientPrivilege:pass
                    else:raise AssertionError('Public API role unexpectedly read private history')
                conn.rollback()
            finally:conn.close()
        assert q("SELECT relrowsecurity FROM pg_class WHERE oid='portfolio_analytics.crypto_snapshots'::regclass")==[(True,)]
        passed('anon authenticated and BYPASSRLS service role have no access to the private RLS table')
        conn=ctx.connect()
        with conn.cursor() as c:
            initialize(c);c.execute("INSERT INTO portfolio_analytics.crypto_snapshots VALUES('2026-10-28',CURRENT_TIMESTAMP,%s,CURRENT_TIMESTAMP)",(Json(payload),))
        conn.rollback();conn.close()
        assert q('SELECT count(*) FROM portfolio_analytics.crypto_snapshots')==[(1,)]
        passed('caller rollback retains previous crypto observation and all financial records')

        # Legacy INIT already includes same-day buys. Read-only reconstruction
        # must consult a confirmed receipt without rewriting any old book/cost.
        from logic.realized_opening import create
        from data.repositories import performance
        q("INSERT INTO assets(id,name,ticker,market,portfolio_id) VALUES('s','합성 ETF','QATEST','KR','default')")
        q("INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,original_avg_price) VALUES('h','a','s',17,100,100)")
        for ident,kind,qty in [('init','INIT',17),('buy','BUY',6)]:
            q("INSERT INTO trade_history(id,account_id,asset_id,trade_date,trade_type,quantity,price,currency) VALUES(%s,'a','s','2026-09-28',%s,%s,100,'KRW')",(ident,kind,qty))
        with ctx.connect() as conn,conn.cursor(cursor_factory=qa.psycopg2.extras.RealDictCursor) as c:
            c.execute("SELECT h.*,s.name AS asset_name,s.ticker,s.market FROM holdings h JOIN assets s ON s.id=h.asset_id WHERE h.id='h'")
            h=dict(c.fetchone())
            c.execute("SELECT * FROM trade_history WHERE asset_id='s'");trades=[dict(r) for r in c.fetchall()]
        seed=create('default',h,trades,'synthetic-opening',datetime(2026,10,17,tzinfo=KST))
        q("INSERT INTO bookkeeping_requests(scope,request_id,payload,result) VALUES('realized-opening:default','synthetic-opening','{}',%s)",
          (Json({'kind':'REALIZED_OPENING','positions':[seed]}),))
        q("INSERT INTO market_cache(key,data) VALUES('div_KR_QATEST',%s)",(Json([{'date':'2026-09-30','amount':1}]),))
        book={'accounts':[dict(id='a',account_no='QA',account_alias='합성',account_type='ISA',deposit_krw=20,deposit_usd=0)],
              'assets':[dict(id='s',name='합성 ETF',ticker='QATEST',market='KR',target_weight=100,is_active=True)],'holdings':[h]}
        old={'ledger':book,'prices':{'s':dict(id='s',price_krw=110,price_native=110)},'fx':{'rate':1400}}
        q("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES('default','2026-10-05',1890,%s,'baseline')",(Json(old),))
        before=unchanged();period_before=performance.read(ctx,'default')
        for _ in range(2):
            restored=repo.read(ctx,'default',False)['rows'][0]
            assert restored['status']=='COMPLETE' and restored['profit_krw']==187 and restored['cost_krw']==1700
            public_result=json.dumps(restored,default=str)
            assert 'covered_trades' not in public_result and 'account_no' not in public_result
        assert unchanged()==before and performance.read(ctx,'default')==period_before
        passed('legacy reconstruction reuses confirmed quantity without changing holdings cash trades receipts NAVs or period results')

        # Optional prior release archive: an offline copy only. The original
        # archive is read, never modified; guarded() still permits only loopback.
        archive=os.environ.get('HISTORY_QA_BACKUP')
        if archive:
            archive=Path(archive).resolve();assert archive.is_file() and archive.suffix=='.dump'
            archive_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
            admin=qa.guarded(**{**qa.settings,'dbname':'postgres'});admin.autocommit=True
            with admin.cursor() as c:
                c.execute('DROP DATABASE '+qa.DB)
                c.execute('CREATE DATABASE '+qa.DB)
            admin.close()
            # pg_dump includes CREATE SCHEMA public; the new empty database
            # already has it. No CASCADE: this must be the empty local schema.
            q('DROP SCHEMA public')
            restore_env={**env,'PGPASSWORD':qa.settings['password'],'PGPASSFILE':'NUL','PGSSLMODE':'disable'}
            with (qa.RUN/'archive-restore.log').open('wb') as log:
                subprocess.run([str(qa.BIN/'pg_restore.exe'),'--no-owner','--no-privileges','--exit-on-error',
                    '-h','127.0.0.1','-p',str(qa.PORT),'-U',qa.settings['user'],'-d',qa.DB,str(archive)],
                    env=restore_env,stdout=log,stderr=log,creationflags=flags,check=True)
            before=unchanged()
            pids=[r[0] for r in q('SELECT id FROM portfolios ORDER BY id')]
            periods_before=[performance.read(ctx,pid) for pid in pids]
            counts=[]
            for pid in pids:
                result=repo.read(ctx,pid,False)
                observed={str(r[0]) for r in q('SELECT snapshot_date FROM performance_snapshots WHERE portfolio_id=%s',(pid,))}
                rows=[r for r in result['rows'] if r['date'] in observed]
                counts.append({'observations':len(rows),'complete':sum(r['status']=='COMPLETE' for r in rows)})
            assert all(row['observations']==row['complete'] for row in counts), 'Archived observations remain unverified'
            assert unchanged()==before
            assert [performance.read(ctx,pid) for pid in pids]==periods_before
            assert hashlib.sha256(archive.read_bytes()).hexdigest()==archive_hash
            report['offline_archive']={'source_sha256':archive_hash,'portfolio_counts':counts,
                'protected_tables_unchanged':len(before),'period_results_unchanged':True,'source_archive_unchanged':True}
            passed('offline archived books are queried without modifying the source backup any restored financial row or original period calculation')
        report.update(status='passed',check_count=len(report['checks']))
    finally:
        if pw.exists():pw.unlink()
        if started:
            p=subprocess.run([str(qa.BIN/'pg_ctl.exe'),'-D',str(cluster),'-m','fast','-w','stop'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            report['isolated_cluster_stopped']=p.returncode==0
        (ROOT/'docs/holding-history-postgres-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
