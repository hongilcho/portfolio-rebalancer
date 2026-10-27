"""Disposable loopback PostgreSQL: history/read purity/privacy/duplicate capture."""
import os,sys,json,subprocess,socket,uuid
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
    def unchanged():return [q('SELECT row_to_json(t) FROM '+table+' t ORDER BY row_to_json(t)::text') for table in ['accounts','holdings','trade_history','performance_snapshots','performance_tracking','performance_flows']]
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
        report.update(status='passed',check_count=len(report['checks']))
    finally:
        if pw.exists():pw.unlink()
        if started:
            p=subprocess.run([str(qa.BIN/'pg_ctl.exe'),'-D',str(cluster),'-m','fast','-w','stop'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            report['isolated_cluster_stopped']=p.returncode==0
        (ROOT/'docs/holding-history-postgres-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
