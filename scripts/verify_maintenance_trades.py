"""Trade equivalence and transaction QA against this task's synthetic PG only.

Reuses the loopback/cluster allowlist from verify_maintenance_refactor. No config,
production dump or external API is read. --reset replaces named QA DBs only.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime
import itertools
import json
import threading
import time

import verify_maintenance_refactor as qa


class TrackedConnection(qa.Connection):
    def commit(self):
        self.queries.append(('COMMIT', None))
        return self.raw.commit()

    def rollback(self):
        self.queries.append(('ROLLBACK', None))
        return self.raw.rollback()

    def close(self):
        self.queries.append(('CLOSE', None))
        return self.raw.close()


def tracked_context(pg, name, trace):
    from data.repository_context import RepositoryContext
    sequence = itertools.count(1)
    def connect():
        raw = pg.connect(host='127.0.0.1', port=qa.PORT, user='refactor_test', dbname=name,
                         options='-c statement_timeout=15000 -c lock_timeout=10000')
        return TrackedConnection(raw, trace)
    return RepositoryContext(connect, lambda:f'entry-{next(sequence):08}', lambda:None, lambda:1300)


def seed(ctx):
    from psycopg2.extras import Json
    policy = {'KR':[{'from':'2026-01-01','rate_pct':'0.0141639'}],
              'US':[{'from':'2026-01-01','rate_pct':'0.07'}]}
    with ctx.connect() as conn, conn.cursor() as c:
        for aid, market in [('kr','KR'),('usd','US'),('managed','US')]:
            c.execute('''INSERT INTO accounts(id,account_no,account_alias,account_type,
                portfolio_id,deposit_krw,deposit_usd,fee_schedule)
                VALUES(%s,%s,%s,'GENERAL','default',1000000,10000,%s)''',
                (aid,'QA-'+aid,aid,Json(policy)))
            c.execute('''INSERT INTO assets(id,name,ticker,market,portfolio_id,allowed_accounts)
                VALUES(%s,%s,%s,%s,'default',%s)''',
                (aid,aid,'QA'+aid,market,Json([aid])))
        c.execute("INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload) VALUES('default','2026-01-01',1000000,%s)",(Json({}),))
        c.execute("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload) VALUES('default','2026-01-01',1000000,%s)",(Json({'holding_metrics':{'status':'COMPLETE','profit_krw':0,'cost_krw':1000000,'return_pct':0}}),))
        conn.commit()
    from data.repositories import forex
    ok, message = forex.record_cash_event(ctx,'managed','OPENING','2026-01-01T00:00:00+09:00',rate=1300)
    assert ok, message


def canonical(value):
    if hasattr(value, 'adapted'):
        return canonical(value.adapted)
    if isinstance(value, dict):
        return {k:('<generated-time>' if k in ('created_at','updated_at','recorded_at','started_at') and v is not None else canonical(v)) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [canonical(v) for v in value]
    return value


def state(ctx):
    from psycopg2 import sql
    result = {}
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname='public' OR schemaname LIKE 'portfolio_%%' ORDER BY 1,2")
        for schema, table in c.fetchall():
            c.execute(sql.SQL('SELECT row_to_json(t) FROM {}.{} t').format(sql.Identifier(schema),sql.Identifier(table)))
            result[schema+'.'+table] = sorted(json.dumps(canonical(r[0]),sort_keys=True,default=str) for r in c.fetchall())
    return result


def trace_value(trace):
    return json.dumps(canonical(trace),sort_keys=True,default=str)


def equivalence(pg, report):
    from data.repositories import trades
    before = qa.baseline_module('data/repositories/trades.py')
    for name in ('refactor_before','refactor_after'):
        qa.prepare(pg,name)
    traces = ([],[])
    contexts = tuple(tracked_context(pg,name,trace) for name,trace in zip(('refactor_before','refactor_after'),traces))
    for ctx in contexts:seed(ctx)
    assert state(contexts[0]) == state(contexts[1])
    cases = [
        ('kr','BUY',10,1000,'2026-01-02',{}),
        ('kr','BUY',20,1100,'2026-01-04',{}),
        ('kr','BUY',1,900,'2026-01-03',{}), # backdated replay
        ('kr','SELL',5,1200,'2026-01-05',{}),
        ('kr','SELL',26,1300,'2026-01-06',{}), # close
        ('kr','BUY',3,1400,'2026-01-07',{'fees_krw':0}),
        ('usd','INIT',2,100.1234,'2026-01-02',{}),
        ('usd','BUY',3,110.34,'2026-01-03',{}),
        ('usd','SELL',2,120.01,'2026-01-04',{}),
        ('managed','BUY',2,100.23,'2026-01-02',{}),
        ('managed','SELL',1,110.56,'2026-01-03',{}),
        ('managed','SELL',1,111.78,'2026-01-04',{}),
        ('managed','BUY',1,100.99,'2026-01-05',{}),
        ('kr','BUY',1,1000,'2026-01-08',{'import_source':'NAMUH_KAKAO','broker_order_no':'12345'}),
    ]
    cases += [
        ('kr','BUY',1,1000,'2026-01-08',{'import_source':'NAMUH_KAKAO','broker_order_no':'12345'}),
        ('kr','BUY',2,1000000,'2026-01-09',{}),
        ('kr','SELL',999,1000,'2026-01-09',{}),
        ('kr','BUY',1,1000,'9999-01-01',{}),
        ('kr','BUY',1,1000,'2026-1-09',{}),
        ('kr','BUY',1,1000,'2026-01-09',{'fees_krw':100000000}),
        ('usd','BUY',1,1000,'2026-01-09',{'exchange_rate':None}),
    ]
    success = failures = 0
    for aid,kind,qty,price,day,extra in cases:
        outputs = [];states = [];sql_traces = []
        for mod,ctx,trace in zip((before,trades),contexts,traces):
            protected=qa.fingerprint(ctx)
            trace.clear()
            args=dict(trade_date=day,account_id=aid,asset_id=aid,trade_type=kind,
                      quantity=qty,price=price,currency='KRW' if aid=='kr' else 'USD',
                      exchange_rate=1 if aid=='kr' else 1327.17,**{})
            args.update(extra)
            result=mod.execute_trade(ctx,**args)
            sql_traces.append(trace_value(trace))
            if not result[0]:assert qa.fingerprint(ctx)==protected, 'Failed trade mutated state'
            outputs.append(result);states.append(state(ctx))
        assert outputs[0]==outputs[1], (aid,kind,outputs)
        assert states[0]==states[1], (aid,kind,'state differs')
        assert sql_traces[0]==sql_traces[1], (aid,kind,'SQL or transaction boundary changed')
        success+=outputs[0][0];failures+=not outputs[0][0]
    # Deletion/replay and batch failure still use the existing transaction owner.
    for mod,ctx in zip((before,trades),contexts):
        with ctx.connect() as conn,conn.cursor() as c:
            c.execute("SELECT id FROM trade_history WHERE account_id='kr' AND trade_date='2026-01-08'")
            ident=c.fetchone()[0]
        assert mod.delete_trades(ctx,[ident])[0]
        protected=qa.fingerprint(ctx)
        try:
            mod.execute_batch(ctx,dict(portfolio_id='default',request_id='qa-batch-fail',trade_date='2026-01-09',trades=[
                dict(account_id='kr',asset_id='kr',trade_type='BUY',quantity=1,price=1000,currency='KRW'),
                dict(account_id='kr',asset_id='kr',trade_type='SELL',quantity=10000,price=1000,currency='KRW')]))
        except ValueError:pass
        else:raise AssertionError('Invalid batch succeeded')
        assert qa.fingerprint(ctx)==protected,'Batch did not roll back all rows/receipt'
    assert state(contexts[0])==state(contexts[1])
    report['trade_equivalence'] = dict(successful_cases=success,rejected_cases=failures,
        complete_financial_state_equal=True,sql_and_transaction_trace_equal=True,
        failed_trade_rollback=True,batch_rollback=True,delete_replay_equal=True)
    return contexts[1]


def concurrency(pg, ctx, report):
    from data.repositories import trades
    # A same-request race must commit one receipt and one cash movement only.
    payload=dict(portfolio_id='default',request_id='qa-concurrent-retry',trade_date='2026-01-10',trades=[
        dict(account_id='kr',asset_id='kr',trade_type='BUY',quantity=1,price=1000,currency='KRW',fees_krw=0)])
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("SELECT deposit_krw FROM accounts WHERE id='kr'");cash=c.fetchone()[0]
        c.execute('SELECT count(*) FROM trade_history');count=c.fetchone()[0]
    gate=threading.Barrier(2)
    def retry():
        gate.wait(timeout=5)
        return trades.execute_batch(ctx,deepcopy(payload))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(retry) for _ in range(2)]
        results=[f.result(timeout=10) for f in futures]
    assert results[0]==results[1] and results[0]['success']
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("SELECT deposit_krw FROM accounts WHERE id='kr'");assert c.fetchone()[0]==cash-1000
        c.execute('SELECT count(*) FROM trade_history');assert c.fetchone()[0]==count+1
        c.execute("SELECT count(*) FROM bookkeeping_requests WHERE request_id='qa-concurrent-retry'");assert c.fetchone()[0]==1
    # Explicit account lock must stop a writer before it reads/spends that cash.
    lock=ctx.connect();c=lock.cursor();c.execute("SELECT id FROM accounts WHERE id='kr' FOR UPDATE")
    started=threading.Event()
    def waiting_buy():
        started.set()
        return trades.execute_trade(ctx,'2026-01-11','kr','kr','BUY',1,1000,'KRW',fees_krw=0)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(waiting_buy)
        assert started.wait(5)
        try:
            # Check PG's actual wait state rather than timing the result alone.
            waiting=False
            for _ in range(60):
                with ctx.connect() as probe,probe.cursor() as p:
                    p.execute("SELECT count(*) FROM pg_stat_activity WHERE datname='refactor_after' AND wait_event_type='Lock' AND query LIKE 'SELECT deposit_krw, deposit_usd%%'")
                    waiting=p.fetchone()[0]>0
                if waiting:break
                time.sleep(.05)
            assert waiting and not future.done(),'Writer bypassed account lock'
        finally:
            lock.rollback()
            lock.close()
        assert future.result(timeout=10)[0]
    # Two separate sales against the same last share cannot both succeed.
    assert trades.execute_trade(ctx,'2026-01-12','kr','kr','INIT',1,1000,'KRW',fees_krw=0)[0]
    gate=threading.Barrier(2)
    def sell():
        gate.wait(timeout=5)
        return trades.execute_trade(ctx,'2026-01-13','kr','kr','SELL',1,1000,'KRW',fees_krw=0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(sell) for _ in range(2)]
        results=[f.result(timeout=10) for f in futures]
    assert sum(r[0] for r in results)==1,results
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("SELECT quantity FROM holdings WHERE account_id='kr'");assert c.fetchone()[0]==0
    report['concurrency'] = dict(one_receipt_one_trade=True,actual_postgres_account_lock_wait=True,
                                simultaneous_sales_no_oversell=True)


def main():
    qa.EVIDENCE.mkdir(parents=True,exist_ok=True)
    pg=qa.isolate();qa.pg=pg
    report={'environment':'dedicated synthetic PostgreSQL only','production_access':False}
    ctx=equivalence(pg,report)
    concurrency(pg,ctx,report)
    (qa.EVIDENCE/'trade-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
