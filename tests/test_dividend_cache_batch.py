"""First-request dividend restoration must preserve values without per-key IO."""
import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from logic import dividend_fetcher as dividends


@pytest.fixture
def cache_batch(mocker):
    mocker.patch.object(dividends, '_dividend_memory_cache', {})
    dividends.begin_dividend_request()
    yield {
        'assets': [{'id': str(i), 'ticker': f'TEST{i}', 'market': 'US', 'name': 'ETF'}
                   for i in range(8)],
        'holdings': [{'asset_id': str(i)} for i in range(8)] + [{'asset_id': '0'}],
        'dividend_cache': {
            f'div_US_TEST{i}': {'data': [{'date': '2026-01-01', 'amount': i+1}], 'age_seconds': 100}
            for i in range(8)
        },
    }
    dividends.begin_dividend_request()


def test_first_request_restores_all_tickers_without_individual_db_reads(cache_batch, mocker):
    db = mocker.patch.object(dividends, 'get_market_cache', side_effect=AssertionError('Extra DB read'))
    external = mocker.patch.object(dividends.yf, 'Ticker', side_effect=AssertionError('External IO'))
    # Simultaneous startup/request restoration is safe and deduplicates holdings.
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(dividends.prepare_dividend_cache, [cache_batch, cache_batch]))
    assert len(dividends._dividend_memory_cache) == 8
    for i in range(8):
        assert dividends.fetch_dividend_history(f'TEST{i}', 'US') == cache_batch['dividend_cache'][f'div_US_TEST{i}']['data']
    db.assert_not_called()
    external.assert_not_called()


def test_seed_retains_age_and_empty_history_is_valid(cache_batch, mocker):
    row = cache_batch['dividend_cache']['div_US_TEST0']
    row['data'] = []
    before = time.time()
    dividends.prepare_dividend_cache(cache_batch)
    external = mocker.patch.object(dividends.yf, 'Ticker')
    assert dividends.fetch_dividend_history('TEST0', 'US') == []
    cache = dividends._dividend_memory_cache['div_US_TEST0']
    assert before-101 <= cache.updated_at <= time.time()-99
    assert not cache.status()['stale']
    external.assert_not_called()


def test_stale_batch_returns_existing_dividends_and_refreshes(cache_batch, mocker):
    cache_batch['dividend_cache']['div_US_TEST0']['age_seconds'] = 90000
    mocker.patch.object(dividends, 'get_market_cache', side_effect=AssertionError('Extra DB read'))
    provider = mocker.patch.object(dividends.yf, 'Ticker', side_effect=RuntimeError('offline'))
    dividends.prepare_dividend_cache(cache_batch)
    assert dividends.fetch_dividend_history('TEST0', 'US') == cache_batch['dividend_cache']['div_US_TEST0']['data']
    cache = dividends._dividend_memory_cache['div_US_TEST0']
    with cache.condition:
        assert cache.condition.wait_for(lambda: not cache.refreshing, timeout=2)
    assert cache.status()['stale'] and cache.status()['refresh_failed']
    assert provider.call_count == 1


def test_missing_row_does_not_become_verified_zero_dividend(cache_batch, mocker):
    del cache_batch['dividend_cache']['div_US_TEST0']
    db = mocker.patch.object(dividends, 'get_market_cache')
    mocker.patch.object(dividends.yf, 'Ticker', side_effect=RuntimeError('offline'))
    dividends.prepare_dividend_cache(cache_batch)
    assert dividends.fetch_dividend_history('TEST0', 'US') == []
    status = dividends.get_dividend_status()
    assert status['updated_at'] is None and status['refresh_failed']
    assert dividends._dividend_memory_cache['div_US_TEST0'].value is None
    db.assert_not_called()


def test_late_batch_cannot_replace_newer_or_refreshing_memory(cache_batch):
    cache = dividends._get_dividend_cache('TEST0', 'US')
    new = [{'date': '2026-01-02', 'amount': 99}]
    cache.seed(new, time.time())
    other = dividends._get_dividend_cache('TEST1', 'US')
    other.refreshing = True
    dividends.prepare_dividend_cache(cache_batch)
    assert cache.value == new
    assert other.value is None and not other.loaded


def test_forced_request_still_collects_once_after_batch_restore(cache_batch, mocker):
    dividends.prepare_dividend_cache(cache_batch)
    cache = dividends._dividend_memory_cache['div_US_TEST0']
    newer = [{'date': '2026-01-02', 'amount': 5}]
    collect = mocker.patch.object(cache, 'fetch', return_value=newer)
    dividends.begin_dividend_request(force=True)
    assert dividends.fetch_dividend_history('TEST0', 'US') == newer
    assert dividends.fetch_dividend_history('TEST0', 'US') == newer
    collect.assert_called_once()


def test_startup_restores_dividends_while_market_collection_is_blocked(cache_batch, mocker):
    from backend import main
    entered, release, restored = threading.Event(), threading.Event(), threading.Event()
    threads = []
    real_thread = threading.Thread

    def thread_factory(*args, **kwargs):
        thread = real_thread(*args, **kwargs)
        threads.append(thread)
        return thread

    def slow_market():
        entered.set()
        assert release.wait(3)

    def prepare(batch):
        dividends.prepare_dividend_cache(batch)
        restored.set()

    mocker.patch.object(main, 'init_db')
    mocker.patch.object(main.market_service, 'warmup', side_effect=slow_market)
    mocker.patch.object(main, 'get_crypto_prices')
    mocker.patch.object(main, 'get_overview_batch_data', return_value=cache_batch)
    mocker.patch.object(main, 'prepare_dividend_cache', side_effect=prepare)
    mocker.patch.object(main.threading, 'Thread', side_effect=thread_factory)

    async def startup():
        async with main.lifespan(main.app):
            assert entered.wait(1)
            assert restored.wait(1), 'Dividend restoration waited for external prices'
            assert dividends._dividend_memory_cache['div_US_TEST0'].loaded

    try:
        asyncio.run(startup())
    finally:
        release.set()
        for thread in threads:
            thread.join(2)
