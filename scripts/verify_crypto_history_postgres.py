"""Fixed-time crypto backfill on a disposable loopback DB, never production."""
import os,sys,json,uuid
from pathlib import Path
from datetime import date,timedelta
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['HISTORY_QA_REPORT']='crypto-history-postgres-evidence.json'
from scripts import verify_holding_history_postgres as suite
from logic import crypto_history as p
from data.repositories import crypto_history as repo,crypto,holding_history,performance


def run(q,ctx,passed):
    q("UPDATE crypto_holdings SET quantity=2,avg_price=100 WHERE owner='홍일' AND symbol='BTC'")
    q("UPDATE crypto_holdings SET quantity=3,avg_price=40 WHERE owner='윤아' AND symbol='ETH'")
    state=repo.state(ctx);rows=state['holdings']
    def quotes(day):
        start=p.cutoff(day)-timedelta(minutes=1)
        return {s:dict(price=price,source='UPBIT',market='KRW-'+s,candle_at=start.isoformat(),
                       last_trade_at=(start+timedelta(seconds=59)).isoformat(),unit=1) for s,price in [('BTC',110),('ETH',50)]}
    ds=p.days('2026-10-05','2026-10-27')
    manifest=p.restore(rows,{str(d):quotes(d) for d in ds},str(ds[0]),str(ds[-1]),p.cutoff(ds[-1])+timedelta(hours=1))
    original=q('SELECT row_to_json(t) FROM portfolio_analytics.crypto_snapshots t ORDER BY snapshot_date')
    financial=lambda:[q('SELECT row_to_json(t) FROM '+table+' t ORDER BY row_to_json(t)::text') for table in ('accounts','assets','holdings','crypto_holdings','trade_history','performance_tracking','performance_snapshots','performance_flows')]
    before=financial();periods=[performance.read(ctx,pid) for pid in ('default','q')]
    result=repo.apply_restore(ctx,manifest,now=p.cutoff(ds[-1])+timedelta(hours=1))
    assert result['inserted']==22 and result['preserved']==1
    assert q("SELECT row_to_json(t) FROM portfolio_analytics.crypto_snapshots t WHERE snapshot_date='2026-10-27'")==original
    assert financial()==before and [performance.read(ctx,pid) for pid in ('default','q')]==periods
    passed('23 daily crypto dates include weekends while existing observations holdings cash trades and period performance stay unchanged')
    frozen=q('SELECT row_to_json(t) FROM portfolio_analytics.crypto_snapshots t ORDER BY snapshot_date')
    result=repo.apply_restore(ctx,manifest,now=p.cutoff(ds[-1])+timedelta(hours=2))
    assert result['inserted']==0 and result['preserved']==23
    assert q('SELECT row_to_json(t) FROM portfolio_analytics.crypto_snapshots t ORDER BY snapshot_date')==frozen
    assert q("SELECT count(*) FROM bookkeeping_requests WHERE scope=%s",(repo.SCOPE,))==[(1,)]
    passed('repeated backfill is idempotent and preserves both the prior daily values and confirmed basis')
    report=holding_history.read(ctx,'crypto',True)
    assert len(report['rows'])==23 and report['coverage']['complete_dates']==23
    public=json.dumps(report,default=str)
    assert all(k not in public for k in ('holdings_fingerprint','holdings_basis','confirmed_start','account_no'))
    assert holding_history.read(ctx,'all',True)['coverage']['complete_dates']==1
    passed('crypto-only and aggregate reads share daily records without exposing private holdings confirmation payloads')
    original_append=repo.append
    def fail(*args):raise RuntimeError('Synthetic journal failure')
    repo.append=fail
    try:success,_=crypto.save_crypto_holding(ctx,'BTC',4,100,owner='홍일')
    finally:repo.append=original_append
    assert not success and financial()==before
    passed('a failed change-journal insert rolls back the holding edit in the same transaction')
    success,_=crypto.save_crypto_holding(ctx,'BTC',4,100,owner='홍일');assert success
    latest=repo.state(ctx)
    assert len(latest['events'])==2
    assert p.basis_at(latest['events'],date(2026,10,26))['fingerprint']==p.fingerprint(rows)
    assert q('SELECT row_to_json(t) FROM portfolio_analytics.crypto_snapshots t ORDER BY snapshot_date')==frozen
    try:repo.apply_restore(ctx,manifest)
    except ValueError:pass
    else:raise AssertionError('Changed holdings accepted against an old backfill basis')
    passed('later edits are journaled without rewriting historical profit and an obsolete restoration basis is rejected')
    payload=p.record(rows,quotes(date(2026,10,26)),date(2026,10,26))
    try:repo.capture(ctx,date(2026,10,26),payload,p.fingerprint(rows))
    except ValueError:pass
    else:raise AssertionError('A concurrent holding edit was ignored')
    assert q('SELECT row_to_json(t) FROM portfolio_analytics.crypto_snapshots t ORDER BY snapshot_date')==frozen
    passed('capture checks current-book and asof-basis fingerprints before committing a historical observation')


suite.EXTRA_CHECKS=run


def archived(q,ctx,passed,report):
    manifest_path=os.environ.get('CRYPTO_QA_MANIFEST')
    if not manifest_path:return
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf8'))
    suite.qa.settings['options']+=' -c extra_float_digits=0'
    from data.repositories.snapshots import get_overview_batch_data
    current=repo.state(ctx)['holdings']
    assert p.fingerprint(current)==manifest['basis']['fingerprint']
    assert p.fingerprint(crypto.get_crypto_holdings(ctx))==p.fingerprint(current)
    assert p.fingerprint(get_overview_batch_data(ctx)['crypto_holdings'])==p.fingerprint(current)
    passed('crypto standalone aggregate and restoration preserve the same stored REAL precision even with extra_float_digits zero')
    tables=('accounts','assets','holdings','crypto_holdings','trade_history','performance_tracking','performance_snapshots','performance_flows')
    frozen=lambda:[q('SELECT row_to_json(t) FROM '+table+' t ORDER BY row_to_json(t)::text') for table in tables]
    before=frozen();pids=[r[0] for r in q('SELECT id FROM portfolios ORDER BY id')]
    periods=[performance.read(ctx,pid) for pid in pids]
    result=repo.apply_restore(ctx,manifest)
    crypto_report=holding_history.read(ctx,'crypto',True)
    combined=holding_history.read(ctx,'all',True)
    excluded=holding_history.read(ctx,'all',False)
    assert len(crypto_report['rows'])==23 and crypto_report['coverage']['complete_dates']==23
    assert combined['coverage']['complete_dates']==14 and excluded['coverage']['complete_dates']==14
    assert all(r['status']=='COMPLETE' for r in combined['rows'] if r['date']>='2026-10-07')
    assert frozen()==before and [performance.read(ctx,pid) for pid in pids]==periods
    report['archived_crypto_restore']={'crypto_days':23,'combined_complete_days':14,
        'financial_only_complete_days':14,'protected_tables_unchanged':len(tables),
        'original_period_results_unchanged':True,'local_inserted':result['inserted']}
    passed('actual offline backup plus public candles restores 23 crypto days and 14 combined financial days without altering original books or period results')


suite.EXTRA_ARCHIVE_CHECKS=archived
suite.qa.PORT=55448;suite.qa.DB='crypto_history_qa'
suite.qa.settings.update(port=suite.qa.PORT,dbname=suite.qa.DB)
suite.qa.RUN=ROOT/'backups/local_validation'/('crypto_history_'+uuid.uuid4().hex)
if __name__=='__main__':suite.main()
