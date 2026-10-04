"""Cache timing/concurrency tests with deterministic blocked external providers."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from logic.refreshing_cache import RefreshingCache, MarketRefreshUnavailable
from backend.services import MarketStateService
from logic import dividend_fetcher as dividends
from logic import crypto_price_fetcher as crypto


def test_stale_read_does_not_wait_and_background_updates_once():
    entered, release = threading.Event(), threading.Event()
    calls = []
    def fetch():
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return 'new'
    cache = RefreshingCache(60, lambda: ('old', 120), fetch)
    try:
        with ThreadPoolExecutor(2) as pool:
            value, status = pool.submit(cache.get).result(timeout=1)
            assert entered.wait(1)
            assert value == 'old' and status['stale'] and status['refreshing']
            assert pool.submit(cache.get).result(timeout=1)[0] == 'old'
            assert len(calls) == 1
            release.set()
            with cache.condition:
                cache.condition.wait_for(lambda: not cache.refreshing, timeout=2)
            assert cache.get()[0] == 'new'
            assert not cache.get()[1]['stale']
    finally:
        release.set()


def test_force_and_cold_callers_share_running_refresh_and_wait():
    entered, release = threading.Event(), threading.Event()
    waiting = threading.Event()
    calls = []
    def fetch():
        calls.append(1); entered.set()
        assert release.wait(3)
        return 42
    cache = RefreshingCache(60, lambda: (None, 0), fetch)
    original_wait = cache.condition.wait
    def wait(timeout=None):
        waiting.set()
        return original_wait(timeout)
    cache.condition.wait = wait
    with ThreadPoolExecutor(2) as pool:
        try:
            first = pool.submit(cache.get)
            assert entered.wait(1)
            second = pool.submit(cache.get, True)
            assert waiting.wait(1)
            assert not first.done() and not second.done()
            release.set()
            assert first.result(2)[0] == second.result(2)[0] == 42
            assert len(calls) == 1
        finally: release.set()


def test_failed_refresh_preserves_cache_and_throttles_retry():
    calls = []
    def fetch():
        calls.append(1)
        raise ValueError('provider offline')
    cache = RefreshingCache(60, lambda: ('old', 120), fetch)
    cache.get()
    with cache.condition:
        assert cache.condition.wait_for(lambda: not cache.refreshing, timeout=2)
    assert cache.get()[0] == 'old'
    assert cache.status()['refresh_failed']
    assert len(calls) == 1
    with pytest.raises(MarketRefreshUnavailable): cache.get(force=True)
    assert cache.get()[0] == 'old' and len(calls) == 2


def test_missing_cache_failures_do_not_loop_external_requests():
    calls = []
    def fail(): calls.append(1); raise ValueError('offline')
    cache = RefreshingCache(60, lambda: (None, 0), fail)
    for _ in range(3):
        with pytest.raises(MarketRefreshUnavailable): cache.get()
    assert len(calls) == 1


def test_invalidation_discards_old_inflight_snapshot():
    entered, release = threading.Event(), threading.Event()
    def fetch(): entered.set(); assert release.wait(3); return 'incompatible'
    cache = RefreshingCache(60, lambda: ('old', 120), fetch)
    try:
        cache.get(); assert entered.wait(1)
        cache.invalidate()
        release.set()
        with cache.condition:
            assert cache.condition.wait_for(lambda: not cache.refreshing, timeout=2)
        assert cache.value == 'old' and cache.updated_at == 0
    finally: release.set()


def test_actual_market_snapshot_keeps_its_fx_during_background_change(mocker):
    service = MarketStateService()
    old = {'prices': [{'id': 'a', 'price_krw': 1400, 'usd_krw': 1400}], 'usd_krw': 1400, 'rate_source': 'old'}
    service._cache.seed(old, time.time()-400)
    entered, release = threading.Event(), threading.Event()
    mocker.patch('backend.services.get_all_assets', return_value=[{'id': 'a'}])
    mocker.patch('backend.services.get_exchange_rate_usd_krw', return_value=(1500, 'new'))
    mocker.patch('backend.services.save_market_cache')
    def fetch(*args): entered.set(); assert release.wait(3); return ([{'id':'a','ticker':'A','price_krw':1500,'usd_krw':1500}],1500)
    mocker.patch('backend.services.fetch_asset_prices', side_effect=fetch)
    try:
        prices, _ = service.get_prices()
        assert entered.wait(1)
        release.set()
        with service._cache.condition:
            assert service._cache.condition.wait_for(lambda: not service._cache.refreshing, timeout=2)
        assert prices[0]['price_krw'] == 1400
        assert service.request_snapshot()['usd_krw'] == 1400
        assert service.request_status()['stale']
        service.get_prices()
        assert service.request_snapshot()['usd_krw'] == 1500
    finally: release.set()


def test_empty_dividend_history_is_a_valid_persistent_cache(mocker):
    mocker.patch.object(dividends, '_dividend_memory_cache', {})
    mocker.patch.object(dividends, 'get_market_cache', return_value=([], 10))
    provider = mocker.patch.object(dividends.yf, 'Ticker')
    dividends.begin_dividend_request()
    assert dividends.fetch_dividend_history('FAKE', 'US') == []
    assert dividends.fetch_dividend_history('FAKE', 'US') == []
    provider.assert_not_called()
    assert not dividends.get_dividend_status()['stale']


def test_dividend_failure_reuses_stale_history_without_retry_storm(mocker):
    mocker.patch.object(dividends, '_dividend_memory_cache', {})
    records = [{'date':'2026-01-01','amount':1}]
    mocker.patch.object(dividends, 'get_market_cache', return_value=(records, 90000))
    provider = mocker.patch.object(dividends.yf, 'Ticker', side_effect=RuntimeError('offline'))
    dividends.begin_dividend_request()
    assert dividends.fetch_dividend_history('FAKE','US') == records
    cache = dividends._dividend_memory_cache['div_US_FAKE']
    with cache.condition: assert cache.condition.wait_for(lambda: not cache.refreshing, timeout=2)
    assert dividends.fetch_dividend_history('FAKE','US') == records
    assert dividends.get_dividend_status()['refresh_failed']
    assert provider.call_count == 1


def test_force_dividend_request_collects_once_per_ticker(mocker):
    mocker.patch.object(dividends, '_dividend_memory_cache', {})
    mocker.patch.object(dividends, 'get_market_cache', return_value=([], 10))
    mocker.patch.object(dividends, 'save_market_cache')
    provider = mocker.patch.object(dividends.yf, 'Ticker')
    provider.return_value.dividends = None
    dividends.begin_dividend_request(True)
    try:
        dividends.fetch_dividend_history('FAKE','US')
        dividends.fetch_dividend_history('FAKE','US')
        assert provider.call_count == 1
    finally: dividends.begin_dividend_request()


def test_partial_crypto_collection_does_not_erase_known_prices(mocker):
    old={'BTC':{'price':100},'ETH':{'price':10}}
    cache = RefreshingCache(60, lambda: (old, 120), crypto._fetch_crypto_snapshot)
    mocker.patch.object(crypto, '_crypto_snapshots', cache)
    mocker.patch.object(crypto, '_fetch_crypto_from_external', return_value={'BTC':{'price':200},'ETH':{'price':0}})
    save=mocker.patch.object(crypto, 'save_market_cache')
    assert crypto.get_crypto_prices() == old
    with cache.condition: assert cache.condition.wait_for(lambda: not cache.refreshing, timeout=2)
    assert crypto.get_crypto_prices() == old
    assert crypto.get_crypto_status()['refresh_failed']
    with pytest.raises(MarketRefreshUnavailable): crypto.get_crypto_prices(True)
    save.assert_not_called()


def test_failed_force_refresh_has_http_503(mocker):
    from backend.main import app
    from backend.routers import dashboard
    from fastapi.testclient import TestClient
    mocker.patch.object(dashboard,'get_overview_batch_data',return_value={})
    mocker.patch.object(dashboard.market_service,'get_prices',side_effect=MarketRefreshUnavailable())
    # No lifespan: schema and warmup IO are unnecessary for this response test.
    response=TestClient(app).get('/api/dashboard/bundle?force_refresh=true')
    assert response.status_code == 503


def test_fallback_exchange_rate_is_not_published_as_fresh(mocker):
    service = MarketStateService()
    old={'prices':[{'id':'a','price_krw':1400}], 'usd_krw':1400, 'rate_source':'old'}
    service._cache.seed(old,time.time()-400)
    mocker.patch('backend.services.get_all_assets',return_value=[{'id':'a'}])
    mocker.patch('backend.services.get_exchange_rate_usd_krw',return_value=(1380,'기본값(기본 1380원)'))
    provider=mocker.patch('backend.services.fetch_asset_prices')
    with pytest.raises(MarketRefreshUnavailable): service.get_prices(True)
    assert service._cache.value == old
    provider.assert_not_called()


def test_empty_provider_response_does_not_erase_known_dividends(mocker):
    mocker.patch.object(dividends, '_dividend_memory_cache', {})
    records=[{'date':'2026-01-01','amount':1}]
    mocker.patch.object(dividends,'get_market_cache',return_value=(records,90000))
    provider=mocker.patch.object(dividends.yf,'Ticker')
    provider.return_value.dividends = None
    save=mocker.patch.object(dividends,'save_market_cache')
    dividends.begin_dividend_request(True)
    try:
        with pytest.raises(MarketRefreshUnavailable): dividends.fetch_dividend_history('FAKE','US')
        assert dividends._dividend_memory_cache['div_US_FAKE'].value == records
        save.assert_not_called()
    finally: dividends.begin_dividend_request()


def test_us_prices_start_before_domestic_batch_finishes(mocker):
    from logic import price_fetcher
    us_started = threading.Event()
    def batch(tickers):
        assert us_started.wait(2), 'US request was unnecessarily blocked by domestic batch'
        return {'KR_TEST':100}
    def single(asset, rate, now, batch_prices):
        if asset['market'] == 'US': us_started.set()
        else: assert batch_prices['KR_TEST'] == 100
        return {'id':asset['id']}
    mocker.patch.object(price_fetcher,'fetch_kr_stocks_batch',side_effect=batch)
    mocker.patch.object(price_fetcher,'_fetch_single_asset_price',side_effect=single)
    assets=[{'id':'kr','market':'KR','ticker':'KR_TEST'}, {'id':'us','market':'US','ticker':'US_TEST'}]
    prices, rate=price_fetcher.fetch_asset_prices(assets,1400)
    assert prices == [{'id':'kr'},{'id':'us'}] and rate == 1400
