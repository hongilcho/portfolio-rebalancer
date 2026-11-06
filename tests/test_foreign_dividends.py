"""Synthetic currency-safe receipts and issuer completeness; no external IO."""
from copy import deepcopy
from datetime import date
import html,json
import pytest
from logic.dividend_calculator import calculate_holding_dividends
from logic.holding_valuation import dividend_profits
from logic.market_providers.ishares import parse_distributions,incomplete,reconcile_sgov


def receipt(**changes):
    return dict(kind='DIVIDEND',dividend_currency='USD',event_date='2026-11-06',reference_date='2026-11-02',dividend_ex_date='2026-11-02',usd_amount=41.4,gross_amount=41.4,tax_amount=0,fee_amount=0,krw_tax=8540,receipt_rate=1355.2,**changes)

def calculate(records):
    h=dict(quantity=148,avg_price_usd=100,avg_price=134000,first_buy_date='2026-10-01',dividend_receipts=[receipt()])
    trades=[dict(trade_date='2026-10-01',trade_type='INIT',quantity=126),dict(trade_date='2026-11-05',trade_type='BUY',quantity=22)]
    before=deepcopy((h,trades,records))
    result=calculate_holding_dividends(h,dict(market='US',ticker='SGOV',name='SGOV'),1355.2,'일반',trades,records)
    assert (h,trades,records)==before
    return result


def test_actual_usd_replaces_estimate_and_krw_tax_is_not_a_second_usd_withholding():
    result=calculate([dict(date='2026-11-02',amount=.328581)])
    assert result['total_dividend_profit']==41.4 and result['total_gross_dividend_profit']==41.4
    assert result['dividend_tax_krw']==8540 and result['dividend_count']==1
    krw,usd=dividend_profits(result,148,True,1355.2)
    assert krw==pytest.approx(41.4*1355.2-8540)
    assert usd==pytest.approx(krw/1355.2)
    assert result['dividend_details'][0]['holding_quantity']==126


def test_receipt_is_preserved_when_public_source_is_empty_then_recovers():
    empty=calculate([]);filled=calculate([dict(date='2026-11-02',amount=.328581)])
    assert empty['total_dividend_profit']==filled['total_dividend_profit']==41.4
    assert empty['dividend_tax_krw']==filled['dividend_tax_krw']==8540
    assert empty['dividend_count']==filled['dividend_count']==1


def issuer_page(**changes):
    columns={'exDate':[20261102,20261001],'payableDate':[20261105,20261006],'totalDistribution':['0.328581','0.300547']}
    columns.update(changes)
    return html.escape(json.dumps({k:{'name':k,'fullName':'performance.distributions.table.'+k,'value':v} for k,v in columns.items()}))


def test_official_table_preserves_precision_dates_and_overrides_incomplete_yahoo():
    source=parse_distributions(issuer_page())
    merged=reconcile_sgov([dict(date='2026-09-01',amount=.307)],source,date(2026,11,6))
    assert [r['date'] for r in merged]==['2026-09-01','2026-10-01','2026-11-02']
    assert merged[-1]==dict(date='2026-11-02',amount=.328581,payment_date='2026-11-05',source='ISHARES')
    assert incomplete('SGOV','US',merged,date(2026,11,6)) is False
    assert incomplete('SGOV','US',merged[:1],date(2026,11,6)) is True
    assert incomplete('VT','US',[],date(2026,11,6)) is False


@pytest.mark.parametrize('changes',[dict(payableDate=[20261105]),dict(totalDistribution=['NaN','0.3']),dict(exDate=[20261102,20261102]),dict(payableDate=[20261001,20261006])])
def test_issuer_structure_or_values_fail_closed(changes):
    with pytest.raises(ValueError):parse_distributions(issuer_page(**changes))


def test_stale_fallback_cannot_be_marked_as_complete():
    with pytest.raises(ValueError):reconcile_sgov([],parse_distributions(issuer_page()),date(2027,2,1))


def test_future_announcements_are_not_earned_dividends():
    records=reconcile_sgov([],parse_distributions(issuer_page()),date(2026,10,15))
    assert [d['date'] for d in records]==['2026-10-01']


def test_cache_fetch_fills_partial_yahoo_with_issuer_without_extra_account_queries(mocker):
    from logic import dividend_fetcher as df
    mocker.patch.object(df,'_dividend_memory_cache',{})
    mocker.patch.object(df,'get_market_cache',return_value=(None,0))
    save=mocker.patch.object(df,'save_market_cache')
    mocker.patch.object(df.YahooQuotes,'dividends',return_value=[dict(date='2026-09-01',amount=.307)])
    mocker.patch.object(df,'fetch_sgov',return_value=parse_distributions(issuer_page()))
    original=df.reconcile_sgov
    mocker.patch.object(df,'reconcile_sgov',side_effect=lambda a,b:original(a,b,date(2026,11,6)))
    mocker.patch.object(df,'incomplete',side_effect=lambda t,m,r:incomplete(t,m,r,date(2026,11,6)))
    df.begin_dividend_request();records=df.fetch_dividend_history('SGOV','US')
    assert records[-1]['amount']==.328581 and save.call_count==1
    assert 'incomplete_symbols' not in df.get_dividend_status()


def test_partial_data_failure_is_visible_and_never_saved_as_fresh_zero(mocker):
    from logic import dividend_fetcher as df
    mocker.patch.object(df,'_dividend_memory_cache',{})
    mocker.patch.object(df,'get_market_cache',return_value=(None,0))
    save=mocker.patch.object(df,'save_market_cache')
    mocker.patch.object(df.YahooQuotes,'dividends',return_value=[dict(date='2026-09-01',amount=.307)])
    mocker.patch.object(df,'fetch_sgov',side_effect=RuntimeError('offline'))
    mocker.patch.object(df,'incomplete',side_effect=lambda t,m,r:incomplete(t,m,r,date(2026,11,6)))
    df.begin_dividend_request();assert df.fetch_dividend_history('SGOV','US')==[]
    status=df.get_dividend_status()
    assert status['incomplete_symbols']==['SGOV'] and status['refresh_failed']
    save.assert_not_called()


def test_recent_monthly_gap_is_flagged_even_when_latest_event_is_fresh():
    assert incomplete('SGOV','US',[dict(date='2026-09-01',amount=.3),dict(date='2026-11-02',amount=.3)],date(2026,11,6))


def test_historical_zero_distribution_does_not_discard_valid_recent_issuer_rows():
    rows=parse_distributions(issuer_page(exDate=[20261102,20210301],payableDate=[20261105,20210305],totalDistribution=['0.328581','0.0']))
    assert len(rows)==1 and rows[0]['date']=='2026-11-02'
