from copy import deepcopy
from datetime import date,datetime,timedelta
from unittest.mock import Mock
import pytest
from logic.holding_history import financial,crypto,combine,history,from_kpi
from backend.holding_history_capture import CryptoCapture,enrich
from logic.close_calendar import KST,cutoff

def sample():
    from test_valuation_refactor import sample_snapshot
    batch,quotes,fx=sample_snapshot()
    batch=deepcopy(batch);ids={a['id'] for a in batch['accounts'] if a['portfolio_id']=='default'}
    batch['accounts']=[a for a in batch['accounts'] if a['id'] in ids]
    batch['holdings']=[h for h in batch['holdings'] if h['account_id'] in ids]
    batch['assets']=[a for a in batch['assets'] if a['portfolio_id']=='default']
    batch['dividend_cache']={f"div_{a['market']}_{a['ticker'].upper()}":{'data':[]} for a in batch['assets']}
    prices={q['id']:{**q,'price_native':q.get('price_usd',0)} for q in quotes}
    return batch,prices,fx

def test_metrics_match_dashboard_including_dividends_but_not_cash_return_denominator():
    from backend.valuation_service import evaluate_portfolio
    from logic.portfolio_valuation import index_valuation_inputs
    from logic.dividend_calculator import calculate_holding_dividends
    batch,prices,fx=sample();before=deepcopy(batch)
    raw=evaluate_portfolio(batch['accounts'],batch['assets'],index_valuation_inputs(batch['holdings'],batch['trade_history'],list(prices.values())),{k:p['price_krw'] for k,p in prices.items()},fx,
        calculate_adjustment=lambda h,a,fx,**kw:calculate_holding_dividends(h,a,fx,dividend_records=[],**kw))
    m=financial(batch,prices,fx,'2026-10-27')
    assert m['status']=='COMPLETE'
    for key,value in from_kpi(raw['kpi']).items():assert m[key]==value
    batch['accounts'][0]['deposit_krw']+=100000
    changed=financial(batch,prices,fx,'2026-10-27')
    assert changed['profit_krw']==m['profit_krw'] and changed['return_pct']==m['return_pct']
    assert changed['value_krw']==pytest.approx(m['value_krw']+100000)
    assert before!=batch

def test_missing_price_cache_or_nonfinite_never_fabricates_history():
    batch,prices,fx=sample()
    assert financial(batch,{},fx,'2026-10-27')['status']=='UNAVAILABLE'
    batch['dividend_cache']={}
    assert financial(batch,prices,fx,'2026-10-27')['profit_krw'] is None
    assert financial(batch,prices,float('nan'),'2026-10-27')['profit_krw'] is None

def test_future_dividends_are_filtered_and_manual_value_uses_frozen_holding():
    batch,prices,fx=sample()
    base=financial(batch,prices,fx,'2026-10-27')
    for row in batch['dividend_cache'].values():row['data']=[{'date':'2099-01-01','amount':1000000}]
    assert financial(batch,prices,fx,'2026-10-27')==base
    batch['holdings'][0]['manual_dividend_override']=100
    manual=financial(batch,prices,fx,'2026-10-27');assert manual['profit_krw']>base['profit_krw']

def test_reconstruction_refuses_unreconciled_trade_quantity():
    batch,prices,fx=sample();batch['trade_history']=[]
    assert financial(batch,prices,fx,'2026-10-27',reconstructed=True)['status']=='UNAVAILABLE'

def metric(cost,profit,value=None):
    return {'version':1,'status':'COMPLETE','source':'RECORDED','cost_krw':cost,'profit_krw':profit,
        'return_pct':profit/cost*100 if cost else None,'value_krw':cost+profit if value is None else value}

def test_aggregation_weights_cost_instead_of_averaging_rates_and_includes_crypto_once():
    a,b,c=metric(100,10,150),metric(900,0,1000),metric(100,-10)
    assert combine([a,b])['return_pct']==pytest.approx(1)
    rows=[{'portfolio_id':pid,'snapshot_date':'2026-10-06','payload':{'holding_metrics':m},'record_kind':'close'} for pid,m in [('p',a),('q',b)]]
    coins=[{'snapshot_date':'2026-10-06','payload':{'metrics':c}}]
    result=history(rows,coins,['p','q'],include_crypto=True)
    assert result['rows'][0]['profit_krw']==0
    assert result['rows'][0]['cost_krw']==1100
    assert history(rows,[],['p','q'],include_crypto=True)['rows'][0]['profit_krw'] is None
    assert history(rows,coins,['p','q'],scope='p')['rows'][0]['profit_krw']==10

def test_missing_components_and_trading_dates_stay_missing_not_zero():
    a=metric(100,10)
    rows=[{'portfolio_id':'p','snapshot_date':day,'payload':{'holding_metrics':a}} for day in ['2026-10-06','2026-10-08']]
    report=history(rows,[],['p'],scope='p')
    assert [r['date'] for r in report['rows']]==['2026-10-06','2026-10-07','2026-10-08']
    assert report['rows'][1]['profit_krw'] is None
    assert history(rows,[],['p','q'])['rows'][0]['profit_krw'] is None

def test_individual_rate_retains_dashboard_precision_instead_of_using_rounded_profit():
    m=metric(100,1);m['return_pct']=1.0049
    rows=[{'portfolio_id':'p','snapshot_date':'2026-10-27','payload':{'holding_metrics':m}}]
    assert history(rows,[],['p'],scope='p')['rows'][0]['return_pct']==1.0049

def test_crypto_matches_owner_universe_and_unknown_price_not_zero():
    holds=[{'owner':'홍일','symbol':'BTC','quantity':2,'avg_price':100},{'owner':'윤아','symbol':'ETH','quantity':1,'avg_price':40}]
    m=crypto(holds,{'BTC':{'price':110},'ETH':{'price':60}})
    assert m['cost_krw']==240 and m['profit_krw']==40
    with pytest.raises(ValueError):crypto(holds,{'BTC':{'price':110}})

def test_crypto_collector_cutoff_window_freshness_idempotency_and_no_historical_guessing():
    now=cutoff(date(2026,10,27));repo=Mock();repo.crypto_exists.return_value=False;repo.capture_crypto.return_value=True
    holds=Mock(return_value=[{'owner':'홍일','symbol':'BTC','quantity':1,'avg_price':100}])
    prices=Mock(return_value={'BTC':{'price':110}});status=Mock(return_value={'updated_at':now.timestamp()})
    worker=CryptoCapture('ctx',holds,prices,status,repo)
    assert not worker.tick(now-timedelta(seconds=1));holds.assert_not_called()
    assert worker.tick(now);assert repo.capture_crypto.call_count==1
    assert not worker.tick(now+timedelta(seconds=10));assert repo.capture_crypto.call_count==1
    repo.crypto_exists.return_value=True
    assert not worker.tick(now+timedelta(minutes=1))
    fresh=CryptoCapture('ctx',holds,prices,status,repo)
    assert not fresh.tick(now+timedelta(minutes=11))
    repo.crypto_exists.return_value=False;status.return_value={'updated_at':now.timestamp()-1}
    assert not CryptoCapture('ctx',holds,prices,status,repo).tick(now)

def test_enrichment_preserves_nav_inputs_and_does_not_require_optional_metrics():
    inputs={'ledger':{},'prices':{},'fx':{'rate':1400},'valuation_at':'stamp'};before=deepcopy(inputs)
    result=enrich(inputs,'2026-10-27')
    assert inputs==before and result['holding_metrics']['status']=='UNAVAILABLE'

def test_delayed_session_does_not_block_next_regular_day_crypto_capture():
    late=cutoff(date(2026,11,19));regular=cutoff(date(2026,11,20));repo=Mock()
    repo.crypto_exists.return_value=True
    worker=CryptoCapture('ctx',lambda:[],lambda:{},lambda:{'updated_at':regular.timestamp()},repo)
    assert not worker.tick(late)
    repo.crypto_exists.return_value=False;repo.capture_crypto.return_value=True
    assert worker.tick(regular)

def test_cold_quote_latency_is_accounted_for_without_backdating_the_capture(monkeypatch):
    now=cutoff(date(2026,10,27));repo=Mock();repo.crypto_exists.return_value=False;repo.capture_crypto.return_value=True
    times=iter([0,20]);monkeypatch.setattr('backend.holding_history_capture.monotonic',lambda:next(times))
    worker=CryptoCapture('ctx',lambda:[],lambda:{},lambda:{'updated_at':now.timestamp()+20},repo)
    assert worker.tick(now)
    assert repo.capture_crypto.call_args.args[2]==now+timedelta(seconds=20)

def test_read_endpoint_precedes_dynamic_route_and_unauthenticated_is_blocked():
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.routers.performance import router
    assert [r.path for r in router.routes].index('/api/performance/holding-history')<[r.path for r in router.routes].index('/api/performance/{pid}')
    assert TestClient(app).get('/api/performance/holding-history').status_code==401

def test_correction_invalidates_holding_metrics_and_cash_correction_preserves_profit():
    from logic.ledger_reconciliation import correct_payload
    payload={'ledger':{'accounts':[{'id':'a','deposit_krw':100}],'holdings':[{'account_id':'a','asset_id':'s','quantity':10}]},
        'prices':{'s':{'price_krw':12}},'holding_metrics':metric(100,20,220)}
    before=deepcopy(payload)
    (fixed,change),error=correct_payload(payload,{'kind':'HOLDING','account_id':'a','asset_id':'s','event_date':'2026-10-27','reason':'합성 정정'},-1)
    assert not error and 'holding_metrics' not in fixed and change==-12
    (fixed,change),error=correct_payload(payload,{'kind':'PAST_WITHDRAWAL','account_id':'a','currency':'KRW','event_date':'2026-10-27','reason':'합성 정정'},-10)
    assert fixed['holding_metrics']['profit_krw']==20 and fixed['holding_metrics']['value_krw']==210
    assert payload==before
