"""Golden provider responses/traces captured from 64cda1d with synthetic IO."""
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from logic import price_fetcher, crypto_price_fetcher, dividend_fetcher
from logic.market_providers.http import QuoteHTTPClient


FIXTURE = Path(__file__).parent / 'fixtures/market_providers_before_refactor.json'


def provider_cases():
    cases = []

    def add(name, kind, args=None, **responses):
        cases.append(dict(name=name, kind=kind, args=args or [], **responses))

    error = {'error': 'offline'}
    failure = {'status': 503}
    add('fx_naver', 'fx', http=[{'json': {'exchangeInfo': {'calcPrice': '1,435.678'}}}])
    add('fx_close_price', 'fx', http=[{'json': {'exchangeInfo': {'closePrice': '1,400'}}}])
    for value in ('500', '-1', 'bad', None):
        add(f'fx_invalid_{value}', 'fx', http=[{'json': {'exchangeInfo': {'calcPrice': value}}}], broker=1420.125)
    add('fx_nh', 'fx', broker=1450.125)
    add('fx_yahoo_fast', 'fx', broker=0, yahoo={'KRW=X': {'fast': 1460.125}})
    add('fx_yahoo_history', 'fx', yahoo={'KRW=X': {'fast': 'nan', 'close': [1470.125]}})
    add('fx_default', 'fx')
    add('fx_all_errors', 'fx', http=[error], broker=error, yahoo={'KRW=X': error})

    add('kr_polling', 'kr', ['005930'], http=[{'json': {'datas': [{'closePrice': '70,100'}]}}])
    add('kr_now_price', 'kr', ['005930'], http=[{'json': {'datas': [{'nowPrice': ' 71000 '}]}}])
    add('kr_mobile', 'kr', ['005930'], http=[failure, {'json': {'nowPrice': '72,000'}}])
    add('kr_nh', 'kr', ['005930'], broker=73000)
    add('kr_invalid_naver', 'kr', ['005930'], http=[{'json': {'datas': [{'closePrice': 'bad'}]}}, {'json': {'closePrice': -1}}], broker=74000)
    add('kr_yahoo_fast', 'kr', ['005930'], yahoo={'005930.KS': {'fast': 75000}})
    add('kr_yahoo_history', 'kr', ['005930'], yahoo={'005930.KS': {'fast': 'nan', 'close': [None, 76000]}})
    add('kr_kq', 'kr', ['005930'], yahoo={'005930.KS': {}, '005930.KQ': {'fast': 77000}})
    add('kr_yahoo_error', 'kr', ['005930'], yahoo={'005930.KS': error})
    add('kr_yahoo_empty', 'kr', ['005930'])

    add('batch_empty', 'batch', [[]])
    add('batch_complete', 'batch', [['0085P0', '476760']], http=[{'json': {'datas': [
        {'itemCode': '0085P0', 'closePrice': '9,545'}, {'itemCode': '476760', 'nowPrice': '8,780'},
    ]}}])
    add('batch_partial_invalid', 'batch', [['A', 'B', 'C', 'D']], http=[{'json': {'datas': [
        {'itemCode': 'A', 'closePrice': '100'}, {'itemCode': 'B', 'closePrice': 'bad'},
        {'itemCode': 'C', 'closePrice': 0}, {'closePrice': 100},
        {'itemCode': 'D', 'closePrice': '-10'},
    ]}}])
    add('batch_timeout', 'batch', [['A']], http=[error])
    add('batch_non_200', 'batch', [['A']])
    add('batch_malformed_json', 'batch', [['A']], http=[{'json_error': 'broken json'}])

    add('us_cached', 'us', ['PDBC', 1400], suffix={'PDBC': 'PDBC.O'}, http=[{'json': {'closePrice': '25.125'}}])
    add('us_discover_then_reuse', 'us', ['NEW', 1400], repeat=2, http=[failure, failure, {'json': {'closePrice': '20.125'}}, {'json': {'nowPrice': '21.125'}}])
    add('us_cached_failure', 'us', ['NEW', 1400], suffix={'NEW': 'NEW.O'}, http=[error, failure, {'json': {'closePrice': '22'}}])
    add('us_explicit_suffix', 'us', ['NEW.K', 1400], http=[failure, {'json': {'closePrice': '23'}}])
    add('us_nh', 'us', ['NEW', 1400], broker=24.12345)
    add('us_yahoo_fast', 'us', ['NEW', 1400], yahoo={'NEW': {'fast': 25.12345}})
    add('us_yahoo_history', 'us', ['NEW', 1400], yahoo={'NEW': {'close': [None, 26.12345]}})
    add('us_yahoo_error', 'us', ['NEW', 1400], yahoo={'NEW': error})
    add('us_yahoo_empty', 'us', ['NEW', 1400])
    for rate in (0, None, -1):
        add(f'us_default_fx_{rate}', 'us', ['NEW', rate], broker=27.1)

    add('gold_nh', 'gold', [1400], broker=135000)
    add('gold_naver_api', 'gold', [1400], http=[{'json': {'closePrice': '201,000'}}])
    add('gold_naver_html', 'gold', [1400], http=[failure, {'content': '<p class="no_today"><span class="blind">202,000</span></p>'}])
    add('gold_yahoo_fast', 'gold', [1400], yahoo={'GC=F': {'fast': 3000.12}})
    add('gold_yahoo_history', 'gold', [1400], yahoo={'GC=F': {'fast': 'nan', 'close': [None, 3100.12]}})
    add('gold_default', 'gold', [1400])
    add('gold_invalid_history', 'gold', [1400], yahoo={'GC=F': {'close': [-1]}})
    add('gold_default_fx', 'gold', [0], yahoo={'GC=F': {'fast': 3000.12}})

    btc = {'market': 'KRW-BTC', 'trade_price': 100000000, 'signed_change_rate': -.012345,
           'high_price': 101000000, 'low_price': 99000000, 'prev_closing_price': 100500000}
    eth = dict(btc, market='KRW-ETH', trade_price=5000000)
    bithumb = {'json': {'data': {'closing_price': '5100000', 'prev_closing_price': '5000000',
                              'max_price': '5200000', 'min_price': '4900000'}}}
    yahoo = {'BTC-KRW': {'close': [99000000, 100000000], 'high': [101000000], 'low': [98000000]},
             'ETH-KRW': {'close': [5000000], 'high': [5100000], 'low': [4900000]}}
    add('crypto_upbit', 'crypto', http=[{'json': [btc, eth]}])
    add('crypto_partial_upbit', 'crypto', http=[{'json': [btc]}, bithumb])
    add('crypto_bithumb', 'crypto', http=[failure, bithumb, bithumb])
    add('crypto_yahoo', 'crypto', yahoo=yahoo)
    add('crypto_mixed_yahoo', 'crypto', http=[{'json': [btc]}, failure], yahoo=yahoo)
    add('crypto_bithumb_error_skips_remaining', 'crypto', http=[failure, error], yahoo=yahoo)
    add('crypto_malformed_after_btc', 'crypto', http=[{'json': [btc, dict(eth, trade_price='bad')]}, bithumb])
    add('crypto_yahoo_partial_failure', 'crypto', yahoo={'BTC-KRW': error, 'ETH-KRW': yahoo['ETH-KRW']})
    add('crypto_missing', 'crypto')

    records = [['2026-08-01', 1.234567], ['2026-01-01', .25], ['2026-02-01', 0],
               ['2026-03-01', -1], ['2026-04-01', None]]
    add('dividend_us', 'dividend', ['abc', 'US'], yahoo={'ABC': {'dividends': records}})
    add('dividend_kr', 'dividend', ['005930', 'KR'], yahoo={'005930.KS': {'dividends': records}})
    add('dividend_kr_suffix', 'dividend', ['005930.KQ', 'KR'], yahoo={'005930.KQ': {'dividends': records}})
    add('dividend_empty', 'dividend', ['ABC', 'US'])
    add('dividend_missing_ticker', 'dividend', ['-', 'KR'])
    return cases


def run_provider_case(case, prices_module=price_fetcher, crypto_module=crypto_price_fetcher,
                      dividend_module=dividend_fetcher):
    trace = []
    pending = iter(copy.deepcopy(case.get('http', [])))

    def http_get(url, headers=None, timeout=None):
        trace.append(['http', url, headers, timeout])
        payload = next(pending, {'status': 503})
        if 'error' in payload:
            raise RuntimeError(payload['error'])

        def json_response():
            if 'json_error' in payload:
                raise ValueError(payload['json_error'])
            return payload.get('json', {})
        return SimpleNamespace(status_code=payload.get('status', 200), json=json_response,
                               content=payload.get('content', '').encode())

    def broker(method, *args, **kwargs):
        trace.append(['nh', method, list(args), kwargs])
        value = case.get('broker')
        if isinstance(value, dict) and 'error' in value:
            raise RuntimeError(value['error'])
        return value

    def ticker(symbol):
        trace.append(['yahoo', symbol])
        payload = case.get('yahoo', {}).get(symbol, {})
        if 'error' in payload:
            raise RuntimeError(payload['error'])
        fast = payload.get('fast')
        fast = float('nan') if fast == 'nan' else fast

        def history(**kwargs):
            trace.append(['history', symbol, kwargs])
            rows = payload.get('close', [])
            if not rows:
                return pd.DataFrame(columns=['Close', 'High', 'Low'])
            return pd.DataFrame({'Close': rows,
                                 'High': (payload.get('high') or [0]) * len(rows),
                                 'Low': (payload.get('low') or [0]) * len(rows)})
        records = payload.get('dividends', [])
        dividends = pd.Series([r[1] for r in records], index=pd.to_datetime([r[0] for r in records]), dtype=float)
        return SimpleNamespace(fast_info=SimpleNamespace(last_price=fast), history=history,
                               dividends=dividends)

    client = SimpleNamespace(
        fetch_exchange_rate=lambda *a, **kw: broker('fx', *a, **kw),
        fetch_current_price=lambda *a, **kw: broker('stock', *a, **kw),
        fetch_gold_price=lambda *a, **kw: broker('gold', *a, **kw),
    )
    output = io.StringIO()
    with contextlib.ExitStack() as stack, contextlib.redirect_stdout(output):
        stack.enter_context(patch.object(prices_module, '_http_get', http_get))
        stack.enter_context(patch.object(prices_module, 'nh_api_client', client))
        suffix = copy.deepcopy(case.get('suffix', {}))
        stack.enter_context(patch.object(prices_module, '_us_ticker_suffix_cache', suffix))
        stack.enter_context(patch.object(prices_module.yf, 'Ticker', ticker))
        if hasattr(crypto_module, '_http_get'):
            stack.enter_context(patch.object(crypto_module, '_http_get', http_get))
        else:
            stack.enter_context(patch.object(crypto_module.requests, 'get', http_get))
        stack.enter_context(patch.object(dividend_module, '_dividend_memory_cache', {}))
        stack.enter_context(patch.object(dividend_module, 'get_market_cache',
                                        lambda key: (trace.append(['cache_read', key]) or (None, 0))))
        stack.enter_context(patch.object(dividend_module, 'save_market_cache',
                                        lambda key, value: trace.append(['cache_save', key, value])))
        dividend_module.begin_dividend_request()
        functions = {'fx': prices_module.get_exchange_rate_usd_krw,
                     'kr': prices_module.get_kr_stock_price, 'us': prices_module.get_us_stock_price,
                     'gold': prices_module.get_krx_gold_price, 'batch': prices_module.fetch_kr_stocks_batch,
                     'crypto': crypto_module._fetch_crypto_from_external,
                     'dividend': dividend_module.fetch_dividend_history}
        values = [functions[case['kind']](*case['args']) for _ in range(case.get('repeat', 1))]
    # JSON canonical form matches tuple/list values in the fixture.
    return json.loads(json.dumps(dict(values=values, trace=trace, suffix=suffix,
                                     stdout=output.getvalue()), ensure_ascii=False))


@pytest.mark.parametrize('case', provider_cases(), ids=lambda case: case['name'])
def test_provider_results_and_call_sequence_match_baseline(case):
    expected = json.loads(FIXTURE.read_text(encoding='utf-8'))['results'][case['name']]
    assert run_provider_case(case) == expected


def test_http_session_is_lazy_shared_and_preserves_timeouts(mocker):
    session = mocker.Mock()
    def create_session():
        time.sleep(.01)  # Concurrent callers overlap the first construction.
        return session
    factory = mocker.Mock(side_effect=create_session)
    client = QuoteHTTPClient(factory)
    factory.assert_not_called()
    with ThreadPoolExecutor(max_workers=8) as executor:
        sessions = list(executor.map(lambda _: client.session(), range(16)))
    assert all(item is session for item in sessions)
    factory.assert_called_once_with()
    assert session.mount.call_count == 2
    adapter = session.mount.call_args_list[0].args[1]
    assert adapter._pool_connections == adapter._pool_maxsize == 20
    client.get('https://example.invalid', headers={'User-Agent': 'fake'}, timeout=2.5)
    session.get.assert_called_once_with('https://example.invalid', headers={'User-Agent': 'fake'}, timeout=2.5)


def test_stock_and_crypto_reuse_the_same_http_client(mocker):
    get = mocker.patch.object(price_fetcher.quote_http_client, 'get')
    price_fetcher._http_get('https://example.invalid/stock', timeout=2)
    crypto_price_fetcher._http_get('https://example.invalid/crypto', timeout=3)
    assert get.call_count == 2
    assert price_fetcher.quote_http_client is crypto_price_fetcher.quote_http_client


def test_mixed_asset_batch_only_refetches_missing_domestic_prices(mocker):
    calls = []
    lock = threading.Lock()

    def http_get(url, headers=None, timeout=None):
        with lock:
            calls.append(url)
        if url.endswith('/A,B'):
            data = {'datas': [{'itemCode': 'A', 'closePrice': '10,000'}]}
        elif url.endswith('/B'):
            data = {'datas': [{'closePrice': '70,000'}]}
        elif url.endswith('/NEW/basic'):
            data = {'closePrice': '101.125'}
        else:
            raise AssertionError(f'Unexpected request: {url}')
        return SimpleNamespace(status_code=200, json=lambda: data)

    mocker.patch.object(price_fetcher, '_http_get', side_effect=http_get)
    mocker.patch.object(price_fetcher, '_us_ticker_suffix_cache', {})
    gold = mocker.patch.object(price_fetcher.nh_api_client, 'fetch_gold_price', return_value=135000)
    yahoo = mocker.patch.object(price_fetcher.yf, 'Ticker', side_effect=AssertionError('Unneeded Yahoo fallback'))

    def asset(id, ticker, market='KR', **values):
        return dict(id=id, name=id, ticker=ticker, market=market, target_weight=0, **values)

    assets = [asset('a', 'A'), asset('us', 'NEW', 'US'), asset('b', 'B'),
              asset('gold', 'M04020000'), asset('deposit', '-', is_deposit=True,
                                             deposit_principal=1000000), asset('manual', '-')]
    prices, rate = price_fetcher.fetch_asset_prices(assets, 1400)
    assert rate == 1400
    assert [p['id'] for p in prices] == [a['id'] for a in assets]
    assert [p['price_krw'] for p in prices] == [10000, 141575, 70000, 135000, 1000000, 0]
    assert prices[1]['price_usd'] == 101.12  # Existing display rounding preserved.
    assert sorted(calls) == sorted([
        'https://polling.finance.naver.com/api/realtime/domestic/stock/A,B',
        'https://polling.finance.naver.com/api/realtime/domestic/stock/B',
        'https://api.stock.naver.com/stock/NEW/basic',
    ])
    gold.assert_called_once_with('M04020000')
    yahoo.assert_not_called()


def test_provider_import_and_construction_have_no_database_or_external_io():
    code = '''
import sys
from unittest.mock import patch
import requests
import psycopg2
with patch.object(requests, 'Session', side_effect=AssertionError('eager session')), \\
     patch.object(psycopg2, 'connect', side_effect=AssertionError('database IO')):
    from logic.market_providers.http import quote_http_client
    from logic.market_providers.sources import QuoteSources
    from logic.market_providers.naver import NaverQuotes
    from logic.market_providers.namuh import NamuhQuotes
    from logic.market_providers.yahoo import YahooQuotes
    from logic.market_providers.crypto import UpbitQuotes, BithumbQuotes
    def forbidden(*args, **kwargs): raise AssertionError('provider IO')
    QuoteSources(NaverQuotes(forbidden, {}), NamuhQuotes(None), YahooQuotes(forbidden))
    UpbitQuotes(forbidden)
    BithumbQuotes(forbidden)
    assert quote_http_client._session is None
    assert 'backend.config' not in sys.modules
    assert 'data.data_manager' not in sys.modules
'''
    env = dict(os.environ, PORTFOLIO_LOAD_CONFIG_FILES='0', SUPABASE_URL='',
               NAMUH_APP_KEY='', NAMUH_APP_SECRET='')
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
