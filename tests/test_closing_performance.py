from copy import deepcopy
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pandas as pd
import pytest
from backend.close_performance import ClosePerformance, start_scheduler
from data.repositories import performance
from logic.close_calendar import KST, cutoff, is_session, previous_session, us_session, sessions
from logic.closing_prices import ClosingPrices, CloseUnavailable
from logic.period_performance import report_periods
from logic.price_fetcher import calculate_deposit_price

DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 16, tzinfo=KST)
ASSET = {'id': 'stock', 'ticker': '0085P0', 'name': 'QA bond', 'market': 'KR'}
BATCH = {'accounts': [{'deposit_krw': 100, 'deposit_usd': 2}],
         'assets': [ASSET], 'holdings': [{'asset_id': 'stock', 'quantity': 3}]}


def http(data):
    return Mock(return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: data))


def test_sessions_holidays_year_end_delayed_close_and_dst():
    for d in [date(2026,10,5),date(2026,7,17),date(2026,6,3),date(2026,12,31)]:
        assert not is_session(d)
    assert previous_session(DAY) == date(2026,10,2)
    assert cutoff(DAY) == NOW
    assert cutoff(date(2026,11,19)).hour == 17
    assert sessions(date(2026,7,16),date(2026,7,20)) == [date(2026,7,16),date(2026,7,20)]
    assert us_session(NOW) == date(2026,10,5)
    assert us_session(datetime(2026,7,6,16,tzinfo=KST)) == date(2026,7,2)
    assert us_session(datetime(2026,1,5,16,tzinfo=KST)) == date(2026,1,2)


def test_calendar_overrides_and_invalid_config(monkeypatch):
    monkeypatch.setenv('PERFORMANCE_KRX_EXTRA_HOLIDAYS','2026-10-06')
    assert not is_session(DAY)
    assert previous_session(date(2026,10,7)) == date(2026,10,2)
    monkeypatch.setenv('PERFORMANCE_KRX_EXTRA_HOLIDAYS','broken')
    with pytest.raises(ValueError): is_session(DAY)


def test_domestic_close_requires_explicit_krx_and_exact_date():
    get = http({'code':'0085P0','stockExchangeType':'KRX','priceInfos':[
        {'localDate':'20261005','closePrice':999}, {'localDate':'20261006','closePrice':10}]})
    q = ClosingPrices(get,Mock(side_effect=AssertionError())).asset(ASSET,DAY,1400)
    assert q['price_date']=='2026-10-06' and q['price_krw']==10
    assert '/chart/domestic/item/0085P0' in get.call_args.args[0]
    provider = ClosingPrices(http({'code':'0085P0','stockExchangeType':'NXT'}),Mock(side_effect=RuntimeError()))
    with pytest.raises(CloseUnavailable): provider.asset(ASSET,DAY,1400)
    with pytest.raises(CloseUnavailable): ClosingPrices.dated([{'localDate':'20261005','closePrice':1}],DAY)


def test_us_close_excludes_current_session_and_preserves_native_price():
    get=http([{'localDate':'20261005','closePrice':19.44},{'localDate':'20261006','closePrice':999}])
    q=ClosingPrices(get).asset({**ASSET,'market':'US','ticker':'PDBC'},DAY,1344.5)
    assert q['price_date']=='2026-10-05' and q['price_native']==19.44
    assert q['price_krw']==pytest.approx(19.44*1344.5)
    assert 'PDBC.O/day' in get.call_args.args[0]


def test_yahoo_fallback_uses_raw_regular_close_without_adjustments():
    bars=pd.DataFrame({'Close':[100],'Adj Close':[80]},index=pd.DatetimeIndex(['2026-10-06'],tz='Asia/Seoul'))
    ticker=SimpleNamespace(history=Mock(return_value=bars))
    q=ClosingPrices(Mock(side_effect=RuntimeError()),lambda _:ticker).asset(ASSET,DAY,1400)
    assert q['price_krw']==100
    opts=ticker.history.call_args.kwargs
    assert opts['auto_adjust'] is False and opts['prepost'] is False
    assert opts['start']=='2026-10-06' and opts['end']=='2026-10-07'


def test_gold_requires_dated_closed_physical_gold_never_futures():
    calls=[{'localTradedAt':'2026-10-06T15:19:49+09:00','marketStatus':'CLOSE'},
           [{'localTradedAt':'2026-10-06T00:00:00+09:00','closePrice':'182,770'}]]
    get=Mock(side_effect=lambda *_,**__: http(calls.pop(0))())
    provider=ClosingPrices(get,Mock(side_effect=AssertionError('No proxy')))
    gold={**ASSET,'ticker':'M04020000'}
    assert provider.asset(gold,DAY,1400)['price_krw']==182770
    provider.get=http({'localTradedAt':'2026-10-06T15:00:00+09:00','marketStatus':'OPEN'})
    with pytest.raises(CloseUnavailable): provider.asset(gold,DAY,1400)


@pytest.mark.parametrize('published,rate', [('2026-10-05T16:00:00+09:00',1400),
    ('2026-10-06T16:01:00+09:00',1400),('2026-10-06T08:00:00+09:00',1400),
    ('2026-10-06T16:00:00',1400),('2026-10-06T15:59:00+09:00',float('nan'))])
def test_stale_future_naive_invalid_fx_is_rejected(published,rate):
    p=ClosingPrices(http({'exchangeInfo':{'localTradedAt':published,'calcPrice':rate}}))
    with pytest.raises(ValueError): p.exchange_rate(NOW)


def test_fx_metadata_and_deposit_interest_use_valuation_date():
    p=ClosingPrices(http({'exchangeInfo':{'localTradedAt':'2026-10-06T15:59:00+09:00','calcPrice':'1,400.25'}}))
    fx=p.exchange_rate(NOW)
    assert fx['rate']==1400.25 and fx['collected_at']==NOW.isoformat()
    dep={'id':'dep','is_deposit':True,'deposit_principal':1000000,'interest_rate':3.65,
         'start_date':'2026-10-01','maturity_date':'2026-10-07','tax_rate':0}
    assert calculate_deposit_price(dep,DAY)[0]==1000500
    assert calculate_deposit_price(dep,date(2026,10,10))[0]==1000600


class Jobs:
    def __init__(self):
        self.tracks=[{'portfolio_id':'p','close_started_on':DAY,'created_at':NOW-timedelta(days=1)}]
        self.job=None
        self.finish_count=0
    def tracking(self,_): return self.tracks
    def schedule(self,_,pid,days,today):
        if self.job is None and days:
            self.job={'portfolio_id':pid,'snapshot_date':days[-1],'state':'pending','inputs':None}
    def claim(self,_,now,pid):
        if self.job and self.job['state'] in ('pending','retry'):
            self.job['state']='running'
            return deepcopy(self.job)
        return None
    def progress(self,_,job,inputs,now): self.job['inputs']=deepcopy(inputs)
    def fail(self,_,job,now,error,missed=False): self.job.update(state='missed' if missed else 'waiting_retry',error=error)
    def finish(self,_,job,value,payload,now):
        self.job.update(state='complete',payload=deepcopy(payload),value=value)
        self.finish_count+=1


def worker(jobs=None):
    jobs=jobs or Jobs()
    quotes=SimpleNamespace(exchange_rate=Mock(return_value={'rate':1400}),
        asset=Mock(side_effect=lambda a,d,fx:{'id':a['id'],'price_krw':10}))
    w=ClosePerformance(ctx=object(),prices=quotes,read_ledger=Mock(return_value=deepcopy(BATCH)),now=lambda:NOW,jobs=jobs)
    return w,jobs,quotes


def test_scheduled_capture_does_not_need_app_view_and_is_idempotent():
    w,jobs,quotes=worker()
    assert w.tick() and jobs.job['value']==2930
    assert not w.tick() and jobs.finish_count==1
    assert quotes.exchange_rate.call_count==w.read_ledger.call_count==1


def test_no_collection_before_cutoff_on_holiday_or_for_late_baseline():
    w,jobs,_=worker()
    w.now=lambda:NOW-timedelta(seconds=1)
    assert not w.tick() and jobs.job is None
    w.now=lambda:datetime(2026,10,5,18,tzinfo=KST)
    assert not w.tick() and jobs.job is None
    w.now=lambda:NOW+timedelta(hours=1)
    jobs.tracks[0]['created_at']=NOW+timedelta(minutes=1)
    assert not w.tick() and jobs.job is None


def test_restart_keeps_original_ledger_fx_and_partial_prices():
    w,jobs,quotes=worker()
    w.read_ledger.return_value['assets'].append({**ASSET,'id':'second'})
    w.read_ledger.return_value['holdings'].append({'asset_id':'second','quantity':1})
    def collect(a,*_):
        if a['id']=='second': raise CloseUnavailable('not published')
        return {'id':a['id'],'price_krw':10}
    quotes.asset.side_effect=collect
    assert not w.tick() and jobs.job['state']=='waiting_retry'
    assert jobs.job['inputs']['prices']['stock']['price_krw']==10
    jobs.job['state']='retry'
    restarted,_,q=worker(jobs)
    restarted.now=lambda:NOW+timedelta(days=1)
    restarted.read_ledger.side_effect=AssertionError('Must use yesterday ledger')
    assert restarted.tick() and jobs.job['value']==2940
    q.exchange_rate.assert_not_called()
    assert q.asset.call_count==1


def test_past_day_without_frozen_ledger_and_fx_is_explicitly_missing():
    w,jobs,q=worker()
    jobs.job={'portfolio_id':'p','snapshot_date':date(2026,10,2),'state':'pending','inputs':{'ledger':BATCH}}
    assert not w.tick() and jobs.job['state']=='missed'
    w.read_ledger.assert_not_called()
    q.exchange_rate.assert_not_called()


def test_old_live_capture_cannot_overwrite_records_and_test_scheduler_is_disabled():
    ctx=SimpleNamespace(connect=Mock(side_effect=AssertionError('No writes')))
    assert performance.capture(ctx,'p',999,{},start=False) is False
    ctx.connect.assert_not_called()
    event,thread=start_scheduler()
    assert thread is None and not event.is_set()


def test_closing_boundaries_use_last_session_not_last_arbitrary_available_quote():
    t={'baseline_date':date(2026,1,2),'baseline_value':100,'close_started_on':date(2026,1,2),
       'revision':0,'confirmed_revision':0,'confirmed_through':date(2026,12,31)}
    snaps=[{'snapshot_date':date(2026,1,30),'value_krw':110,'record_kind':'close'},
           {'snapshot_date':date(2026,2,27),'value_krw':121,'record_kind':'close'}]
    jan,feb=report_periods(t,snaps,[])[:2]
    assert jan['end']==date(2026,1,30) and jan['period_complete']
    assert feb['start']==date(2026,1,30) and feb['end']==date(2026,2,27)
    assert feb['return_pct']==pytest.approx(10)
    missing=report_periods(t,snaps[1:],[])[1]
    assert missing['start_value'] is None and missing['return_pct'] is None
    snaps[0]['record_kind']='legacy_view'
    assert report_periods(t,snaps,[])[0]['end_value'] is None


@pytest.mark.parametrize('baseline', [date(2026,1,30),date(2026,1,31)])
def test_late_or_holiday_month_end_baseline_remains_next_month_start(baseline):
    t={'baseline_date':baseline,'baseline_value':100,'close_started_on':baseline,
       'revision':0,'confirmed_revision':0,'confirmed_through':date(2026,12,31)}
    snaps=[{'snapshot_date':baseline,'value_krw':100,'record_kind':'baseline'},
           {'snapshot_date':date(2026,2,27),'value_krw':110,'record_kind':'close'}]
    feb=report_periods(t,snaps,[])[1]
    assert feb['start']==baseline and feb['start_value']==100
    assert feb['return_pct']==pytest.approx(10)


def test_old_periods_before_close_rollout_keep_legacy_boundary_semantics():
    t={'baseline_date':date(2026,1,2),'baseline_value':100,'close_started_on':date(2026,10,5),
       'revision':0,'confirmed_revision':0,'confirmed_through':date(2026,12,31)}
    snaps=[{'snapshot_date':date(2026,1,31),'value_krw':110,'record_kind':'legacy_view'}]
    jan=report_periods(t,snaps,[])[0]
    assert jan['period_complete'] is None and jan['end']==date(2026,1,31)
    assert jan['return_pct']==pytest.approx(10)
