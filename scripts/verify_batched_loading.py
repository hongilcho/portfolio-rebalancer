"""Synthetic-only, real PostgreSQL differential checks for batched history reads."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
import json
from pathlib import Path
import sys

import verify_maintenance_refactor as qa
qa.PORT=55474
qa.CLUSTER=(qa.ROOT/'backups/batched-loading/cluster').resolve()
qa.EVIDENCE=qa.ROOT/'backups/batched-loading'
qa.BASE='5c24f50ce6e6461194ceb624a9068f57458dce7c'


def main():
    from fastapi.encoders import jsonable_encoder
    from psycopg2.extras import Json
    pg=qa.isolate();qa.pg=pg
    ctx=qa.prepare(pg,'refactor_reads')
    baseline=qa.baseline_module('data/repositories/holding_history.py')
    snapshots_before=qa.baseline_module('data/repositories/snapshots.py')
    from data.repositories import holding_history as current,snapshots
    scenarios=[]

    def check(label):
        protected=qa.fingerprint(ctx)
        views=[]
        for scope,include in [('default',False),('other',False),('all',False),('all',True),('crypto',True),('crypto',False)]:
            old_queries=[];new_queries=[]
            try:
                old=baseline.read(qa.context(pg,queries=old_queries),scope,include)
            except ValueError as exc:
                try:current.read(qa.context(pg,queries=new_queries),scope,include)
                except ValueError as other:assert str(exc)==str(other)
                else:raise AssertionError('Missing scope was accepted')
                views.append(dict(scope=scope,unknown=True))
                continue
            new=current.read(qa.context(pg,queries=new_queries),scope,include)
            assert jsonable_encoder(old)==jsonable_encoder(new), (label,scope,include)
            assert len(new_queries)==2,(label,new_queries)
            assert new_queries[0][0].startswith('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            views.append(dict(scope=scope,include_crypto=include,before_queries=len(old_queries),after_queries=len(new_queries)))
        for scope in ('absent',"' OR TRUE --"):
            errors=[]
            for module in (baseline,current):
                try:module.read(ctx,scope)
                except ValueError as exc:errors.append(str(exc))
            assert len(errors)==2 and errors[0]==errors[1]
        assert qa.fingerprint(ctx)==protected
        scenarios.append(dict(scenario=label,views=views,unknown_scope_blocked=True,financial_tables_unchanged=True))

    check('empty')
    qa.seed_reads(ctx)
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload) VALUES('other','2026-10-05',10000,'{}')")
        c.execute("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind,valuation_at) VALUES('other','2026-10-06',10100,%s,'close','2026-10-06T16:00:00.123456+09:00')",(Json({'holding_metrics':{'status':'COMPLETE','profit_krw':100,'cost_krw':10000,'return_pct':1}}),))
        for day in ('2026-10-05','2026-10-06','2026-10-08'):
            c.execute('INSERT INTO portfolio_analytics.crypto_snapshots(snapshot_date,valuation_at,payload) VALUES(%s,%s,%s)',(day,day+'T16:00:00+09:00',Json({'basis':'SYNTHETIC_1600','metrics':{'status':'COMPLETE','profit_krw':50,'value_krw':1050,'cost_krw':1000,'return_pct':5}})))
        c.execute("UPDATE performance_snapshots SET valuation_at='2026-10-06T16:00:00.123456+09:00' WHERE portfolio_id='default'")
        conn.commit()
    check('frozen_metrics_and_crypto_gaps')
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("SET TRANSACTION READ ONLY")
        from data.repositories.holding_history_batch import HISTORY_SQL
        c.execute(HISTORY_SQL,{'scope':'all','include_crypto':True});raw=c.fetchone()[0]
        assert raw['trades']==[] and raw['cache']=={} and raw['openings']==[]
        conn.rollback()
    batch=snapshots.get_overview_batch_data(ctx,'default',cma_support=False)
    account=next(a for a in batch['accounts'] if a['id']=='default-a0')
    asset=next(a for a in batch['assets'] if a['id']=='default-s0')
    holding=deepcopy(next(h for h in batch['holdings'] if h['account_id']==account['id']))
    holding.update(quantity=30,avg_price=100,original_avg_price=100,first_buy_date='2026-01-01')
    payload=dict(ledger=dict(accounts=[account],assets=[asset],holdings=[holding]),
                 prices={asset['id']:dict(id=asset['id'],price_krw=120)},fx={'rate':1400})
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("UPDATE performance_snapshots SET payload=%s WHERE portfolio_id='default' AND snapshot_date='2026-10-06'",(Json(payload),))
        c.execute("UPDATE market_cache SET data=%s WHERE key='div_KR_QADEFAULT0'",(Json([{'date':'2026-09-01','amount':1}]),))
        # Same public journal storage path as real confirmed openings.
        c.execute("INSERT INTO bookkeeping_requests(scope,request_id,payload,result) VALUES('realized-opening:other','qa-receipt','{}',%s)",(Json({'kind':'REALIZED_OPENING','positions':[]}),))
        conn.commit()
    check('legacy_reconstruction_pre_period_dividends_and_opening_receipt')
    row=next(r for r in current.read(ctx,'default',False)['rows'] if r['date']=='2026-10-06')
    assert row['status']=='COMPLETE' and row['source']=='RECONSTRUCTED' and row['dividend_krw']>0
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO ledger_adjustments(id,portfolio_id,account_id,request_id,event_date,kind,reason,request,before_state,after_state,history) VALUES('qa-correction','default','default-a0','qa','2026-10-06','CASH','synthetic','{}','{}','{}',%s)",(Json([{'date':'2026-10-06','decision':'UNKNOWN'}]),))
        conn.commit()
    check('unconfirmed_legacy_day_skips_replay')
    row=next(r for r in current.read(ctx,'default',False)['rows'] if r['date']=='2026-10-06')
    assert row['status']=='UNCONFIRMED' and row['profit_krw'] is None
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("UPDATE ledger_adjustments SET reversed_at=CURRENT_TIMESTAMP WHERE id='qa-correction'")
        c.execute("UPDATE market_cache SET data='[]'::jsonb")
        conn.commit()
    check('reversed_correction_and_empty_dividend_cache')

    assert snapshots.get_overview_cma_support(ctx) is False
    for enabled in (False,True):
        if enabled:
            with ctx.connect() as conn,conn.cursor() as c:
                c.execute('CREATE SCHEMA portfolio_cma')
                c.execute('CREATE TABLE portfolio_cma.income(portfolio_id text,account_id text,amount_krw numeric,reversed_at timestamptz)')
                c.execute('CREATE TABLE portfolio_cma.openings(LIKE portfolio_cma.income)')
                c.execute("UPDATE accounts SET account_type='CMA' WHERE id='default-a0'")
                c.execute("INSERT INTO portfolio_cma.income VALUES('default','default-a0',123,NULL),('other','default-a0',999,NULL)")
                conn.commit()
        assert snapshots.get_overview_cma_support(ctx) is enabled
        protected=qa.fingerprint(ctx)
        for pid in (None,'default','other'):
            oq=[];nq=[]
            old=snapshots_before.get_overview_batch_data(qa.context(pg,queries=oq),pid)
            new=snapshots.get_overview_batch_data(qa.context(pg,queries=nq),pid,cma_support=enabled)
            assert qa.normalized(old)==qa.normalized(new)
            assert len(oq)==2 and len(nq)==1
        assert qa.fingerprint(ctx)==protected
    report={'status':'SYNTHETIC_POSTGRES_PASSED','history_scenarios':scenarios,
        'scope_cases':len(scenarios)*8,'history_sql_count':2,'dashboard_sql_count':1,
        'frozen_history_omits_replay_inputs':True,'cma_enabled_and_disabled_outputs_equal':True,
        'financial_tables_unchanged':True,'production_access':False}
    (qa.EVIDENCE/'postgres-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
