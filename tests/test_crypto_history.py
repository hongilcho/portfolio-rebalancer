"""No external IO: fixed-time prices, unchanged basis and shared history."""
from copy import deepcopy
from datetime import date,timedelta,timezone
from unittest.mock import Mock
import pytest
from logic import crypto_history as p
from logic.holding_history import history
from backend.holding_history_capture import CryptoCapture
from logic.market_providers.crypto_history import UpbitHistory
from logic.crypto_numbers import stored_real,precise_holding


def test_real_book_fingerprint_uses_stored_precision_not_connection_text_rounding():
    exact=stored_real(.1711176)
    wire=precise_holding({'quantity':.171118,'avg_price':114950000,
        'quantity_precise':exact,'avg_price_precise':stored_real(114950352)})
    assert wire['quantity']==exact and wire['avg_price']==stored_real(114950352)
    assert 'quantity_precise' not in wire
    row=dict(owner='홍일',symbol='BTC',**wire)
    assert p.fingerprint([row])==p.fingerprint([{**row,'quantity':.1711176}])


def holds():return [dict(owner='홍일',symbol='BTC',quantity=2,avg_price=100),dict(owner='윤아',symbol='ETH',quantity=3,avg_price=40)]


def candle(symbol,day,price=110):
    start=p.cutoff(day)-timedelta(minutes=1)
    return [dict(market='KRW-'+symbol,unit=1,trade_price=price,
        candle_date_time_utc=start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
        candle_date_time_kst=start.replace(tzinfo=None).isoformat(),timestamp=int((start.timestamp()+59)*1000))]


def quotes(day):return {s:p.minute_quote(s,day,candle(s,day,price)) for s,price in [('BTC',110),('ETH',50)]}


def test_exact_1559_close_is_used_with_kst_utc_boundaries():
    q=p.minute_quote('BTC',date(2026,10,5),candle('BTC',date(2026,10,5)))
    assert q['price']==110 and q['candle_at']=='2026-10-05T15:59:00+09:00'
    assert q['last_trade_at'].startswith('2026-10-05T06:59:59')


@pytest.mark.parametrize('problem',['empty','symbol','unit','utc','kst','tick','nan','zero'])
def test_missing_wrong_or_lookahead_candles_are_rejected(problem):
    day=date(2026,10,5);rows=candle('BTC',day)
    if problem=='empty':rows=[]
    elif problem=='symbol':rows[0]['market']='BTC-KRW'
    elif problem=='unit':rows[0]['unit']=3
    elif problem=='utc':rows[0]['candle_date_time_utc']='2026-10-05T07:00:00'
    elif problem=='kst':rows[0]['candle_date_time_kst']='2026-10-05T16:00:00'
    elif problem=='tick':rows[0]['timestamp']=int(p.cutoff(day).timestamp()*1000)
    elif problem=='nan':rows[0]['trade_price']=float('nan')
    else:rows[0]['trade_price']=0
    with pytest.raises(ValueError):p.minute_quote('BTC',day,rows)


def test_public_provider_validates_responses_and_never_requests_account_auth():
    day=date(2026,10,5);get=Mock(return_value=Mock(status_code=200,json=lambda:candle('BTC',day)))
    provider=UpbitHistory(get,now=lambda:p.cutoff(day)+timedelta(days=1))
    assert provider.prices(day,{'BTC'})['BTC']['price']==110
    url=get.call_args.args[0]
    assert '/candles/minutes/1?' in url and 'KRW-BTC' in url and 'count=1' in url and '07%3A00%3A00' in url
    assert 'Authorization' not in get.call_args.kwargs['headers']
    get.return_value.status_code=429
    with pytest.raises(ValueError):provider.prices(day,{'BTC'})
    assert get.call_count==2


def test_future_cutoff_is_rejected_before_a_network_call():
    day=date(2026,10,5);get=Mock()
    with pytest.raises(ValueError):UpbitHistory(get,now=lambda:p.cutoff(day)-timedelta(seconds=1)).prices(day)
    get.assert_not_called()


def test_restore_includes_weekends_keeps_cost_and_nonzero_first_profit():
    rows=holds();before=deepcopy(rows);ds=p.days('2026-10-05','2026-10-27')
    result=p.restore(rows,{str(d):quotes(d) for d in ds},str(ds[0]),str(ds[-1]),p.cutoff(ds[-1])+timedelta(hours=1))
    assert len(result['records'])==23 and any(r['date']=='2026-10-10' for r in result['records'])
    first=result['records'][0]['payload']['metrics']
    assert first['cost_krw']==320 and first['profit_krw']==50
    assert first['return_pct']==pytest.approx(50/320*100)
    assert first['source']=='RECONSTRUCTED' and rows==before


def test_backfill_is_all_or_nothing_when_a_price_is_missing():
    with pytest.raises(ValueError):p.restore(holds(),{},'2026-10-05','2026-10-06',p.cutoff('2026-10-27'))


def test_confirmed_period_never_extends_backwards_or_into_an_unobserved_gap():
    observed=p.cutoff('2026-10-28')+timedelta(hours=1)
    event=p.basis_event(holds(),observed,start='2026-10-05',end='2026-10-27')
    assert p.basis_at([event],date(2026,10,5))
    assert p.basis_at([event],date(2026,10,4)) is None
    assert p.basis_at([event],date(2026,10,28)) is None
    assert p.basis_at([event],date(2026,10,29))


def test_later_edits_keep_the_confirmed_past_and_asof_holdings():
    rows=holds();old=p.basis_event(rows,p.cutoff('2026-10-27')+timedelta(hours=1),start='2026-10-05',end='2026-10-27')
    rows[0]['quantity']=4
    changed=p.basis_event(rows,p.cutoff('2026-10-28')+timedelta(hours=1))
    btc=lambda day:next(h['quantity'] for h in p.basis_at([old,changed],day)['holdings'] if h['symbol']=='BTC')
    assert btc(date(2026,10,27))==2
    assert btc(date(2026,10,28))==2
    assert btc(date(2026,10,29))==4
    with pytest.raises(ValueError):p.basis_at([old,p.basis_event(rows,p.cutoff('2026-10-10'))],date(2026,10,10))


def worker(day):
    repo=Mock();rows=holds();event=p.basis_event(rows,p.cutoff(day)-timedelta(hours=1))
    repo.state.return_value={'holdings':rows,'events':[event],'dates':set()};repo.capture.return_value=True
    provider=Mock();provider.prices.side_effect=lambda d,s:quotes(d)
    return CryptoCapture('ctx',provider,repo),repo,provider


def test_collector_waits_until_cutoff_and_throttles_duplicate_passes():
    day=date(2026,10,27);collector,repo,provider=worker(day)
    assert not collector.tick(p.cutoff(day)-timedelta(minutes=2));provider.prices.assert_not_called()
    assert collector.tick(p.cutoff(day))
    assert not collector.tick(p.cutoff(day)+timedelta(seconds=30))
    assert repo.capture.call_count==1 and repo.capture.call_args.args[2]['valuation_at']==p.cutoff(day).isoformat()


def test_weekends_and_late_collection_use_fixed_prices_not_late_spot():
    day=date(2026,10,10);collector,repo,provider=worker(day)
    assert collector.tick(p.cutoff(day)+timedelta(hours=4))
    assert repo.capture.call_args.args[2]['prices']['BTC']['candle_at'].endswith('15:59:00+09:00')
    repo.state.return_value['dates']={str(day)}
    assert not CryptoCapture('ctx',provider,repo).tick(p.cutoff(day)+timedelta(hours=5))
    assert provider.prices.call_count==1


def test_restart_recovers_one_missing_day_using_historical_basis():
    collector,repo,provider=worker(date(2026,10,9))
    assert collector.tick(p.cutoff('2026-10-11'))
    assert repo.capture.call_args.args[1]==date(2026,10,9)
    assert repo.capture.call_args.args[2]['metrics']['source']=='RECONSTRUCTED'


def test_first_observation_after_cutoff_never_invents_todays_holding():
    day=date(2026,10,27);collector,repo,provider=worker(day)
    repo.state.return_value['events']=[]
    repo.observe.return_value=p.basis_event(holds(),p.cutoff(day)+timedelta(hours=2))
    assert not collector.tick(p.cutoff(day)+timedelta(hours=2));provider.prices.assert_not_called()


def test_unjournaled_change_is_rejected_not_used_for_backfill():
    collector,repo,provider=worker(date(2026,10,27))
    repo.state.return_value['holdings']=deepcopy(holds());repo.state.return_value['holdings'][0]['quantity']=9
    with pytest.raises(ValueError):collector.tick(p.cutoff('2026-10-27'))
    provider.prices.assert_not_called();repo.capture.assert_not_called()


def test_one_missing_candle_does_not_block_other_days_forever():
    collector,repo,provider=worker(date(2026,10,9))
    def quote_or_error(day,symbols):
        if day==date(2026,10,9):raise ValueError('Synthetic missing minute')
        return quotes(day)
    provider.prices.side_effect=quote_or_error
    with pytest.raises(ValueError):collector.tick(p.cutoff('2026-10-11'))
    assert collector.tick(p.cutoff('2026-10-11')+timedelta(minutes=1))
    assert repo.capture.call_args.args[1]==date(2026,10,10)


def test_crypto_and_combined_calendars_share_identical_daily_metrics():
    ds=p.days('2026-10-05','2026-10-27')
    manifest=p.restore(holds(),{str(d):quotes(d) for d in ds},str(ds[0]),str(ds[-1]),p.cutoff(ds[-1]))
    coins=[{'snapshot_date':r['date'],'payload':r['payload']} for r in manifest['records']]
    standalone=history([],coins,[],scope='crypto',include_crypto=True)
    assert len(standalone['rows'])==23 and standalone['coverage']['complete_dates']==23
    from logic.close_calendar import sessions
    financial=[{'portfolio_id':pid,'snapshot_date':str(d),'payload':{'holding_metrics':dict(status='COMPLETE',source='RECORDED',cost_krw=100,profit_krw=10,value_krw=120,return_pct=10)}}
        for d in sorted({ds[0],*sessions(ds[0],ds[-1])}) for pid in ('p','q') if pid=='p' or str(d)>='2026-10-07']
    together=history(financial,coins,['p','q'],scope='all',include_crypto=True)
    assert len(together['rows'])==16 and together['coverage']['complete_dates']==14
    first=next(r for r in together['rows'] if r['status']=='COMPLETE')
    assert first['profit_krw']==70 and first['cost_krw']==520
    assert first['return_pct']==pytest.approx(70/520*100)
    assert first['components']['crypto']['profit_krw']==standalone['rows'][2]['profit_krw']
