"""
시장 시세 수집기 및 다중 폴백 단위 테스트 (test_price_fetcher.py)
================================================================
네이버 금융 공식 JSON API(1차) ➔ NH투자증권 Open API(2차) ➔ yfinance(3차)
다중 폴백 체인이 정상적으로 동작하는지 모의(Mock) 환경에서 검증합니다.
"""

import pytest
from logic.price_fetcher import get_kr_stock_price, get_us_stock_price, get_krx_gold_price, get_exchange_rate_usd_krw

def test_get_us_stock_price_naver(mocker):
    """미국 주식 시세 네이버 금융 최우선 수집 및 원화 환산 검증"""
    # Mock Naver API to succeed (1st priority)
    mock_res = mocker.MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {'closePrice': '155.0'}
    mocker.patch('logic.price_fetcher.requests.get', return_value=mock_res)
    
    price, source = get_us_stock_price('AAPL', usd_krw=1380.0)
    assert price == 155.0 * 1380.0
    assert source == "네이버 금융"

def test_get_us_stock_price_nh_fallback(mocker):
    # Mock Naver API to fail
    mocker.patch('logic.price_fetcher.requests.get', side_effect=Exception("Naver Error"))
    # Mock NH API to succeed (2nd fallback)
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_current_price', return_value=150.0)
    
    price, source = get_us_stock_price('AAPL', usd_krw=1380.0)
    assert price == 150.0 * 1380.0
    assert source == "NH API"

def test_get_us_stock_price_yfinance_fallback(mocker):
    # Mock naver and nh_api_client to fail, testing yfinance fallback
    mocker.patch('logic.price_fetcher.requests.get', side_effect=Exception("Naver Error"))
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_current_price', return_value=None)
    
    # Mock yfinance Ticker and history
    mock_ticker = mocker.MagicMock()
    import pandas as pd
    df = pd.DataFrame({'Close': [150.0, 150.5]})
    mock_ticker.history.return_value = df
    mock_ticker.fast_info = None

    mocker.patch('logic.price_fetcher.yf.Ticker', return_value=mock_ticker)
    
    price, source = get_us_stock_price('AAPL', usd_krw=1380.0)
    assert price == 150.5 * 1380.0
    assert source == "yfinance"

def test_get_us_stock_price_fastinfo(mocker):
    mocker.patch('logic.price_fetcher.requests.get', side_effect=Exception("Naver Error"))
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_current_price', return_value=None)
    
    mock_ticker = mocker.MagicMock()
    mock_fast_info = mocker.MagicMock()
    mock_fast_info.last_price = 151.0
    mock_ticker.fast_info = mock_fast_info

    mocker.patch('logic.price_fetcher.yf.Ticker', return_value=mock_ticker)
    
    price, source = get_us_stock_price('AAPL', usd_krw=1380.0)
    assert price == 151.0 * 1380.0
    assert source == "yfinance"

def test_get_kr_stock_price_naver(mocker):
    # Mock Naver Polling API to succeed
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'datas': [{'closePrice': '70000'}]
    }
    mocker.patch('logic.price_fetcher.requests.get', return_value=mock_response)

    price, source = get_kr_stock_price('005930')
    assert price == 70000.0
    assert source == "네이버 금융"

def test_get_kr_stock_price_nh_fallback(mocker):
    # Mock Naver API to fail
    mocker.patch('logic.price_fetcher.requests.get', side_effect=Exception("Naver Error"))
    # Mock NH API to succeed
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_current_price', return_value=71000.0)

    price, source = get_kr_stock_price('005930')
    assert price == 71000.0
    assert source == "NH API"

def test_get_exchange_rate_naver(mocker):
    # Mock Naver exchange JSON API (1st priority)
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'exchangeInfo': {'calcPrice': '1350.5'}
    }
    mocker.patch('logic.price_fetcher.requests.get', return_value=mock_response)
    
    rate, source = get_exchange_rate_usd_krw()
    assert rate == 1350.5
    assert source == "네이버 금융"

def test_get_exchange_rate_nh_fallback(mocker):
    # Mock Naver API to fail
    mocker.patch('logic.price_fetcher.requests.get', side_effect=Exception("Naver Error"))
    # Mock NH API to succeed (2nd fallback)
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_exchange_rate', return_value=1355.0)

    rate, source = get_exchange_rate_usd_krw()
    assert rate == 1355.0
    assert source == "Namuh API"

def test_get_krx_gold_price_nh_first(mocker):
    # For KRX gold, NH API is 1st priority
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_gold_price', return_value=135000.0)

    price, source = get_krx_gold_price()
    assert price == 135000.0
    assert source == "NH API"

def test_fetch_kr_stocks_batch(mocker):
    """국내 주식 콤마 단일 배치 수집 단위 테스트"""
    from logic.price_fetcher import fetch_kr_stocks_batch
    mock_res = mocker.MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        'datas': [
            {'itemCode': '0085P0', 'closePrice': '9,545'},
            {'itemCode': '476760', 'closePrice': '8,780'}
        ]
    }
    mocker.patch('logic.price_fetcher.requests.get', return_value=mock_res)
    res = fetch_kr_stocks_batch(['0085P0', '476760'])
    assert res.get('0085P0') == 9545.0
    assert res.get('476760') == 8780.0

def test_us_stock_suffix_cache(mocker):
    """미국 주식 접미사 캐싱 검증"""
    from logic.price_fetcher import _us_ticker_suffix_cache
    _us_ticker_suffix_cache['TEST_TICKER'] = 'TEST_TICKER.O'

    mock_res = mocker.MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {'closePrice': '25.0'}
    mocker.patch('logic.price_fetcher.requests.get', return_value=mock_res)

    price, source = get_us_stock_price('TEST_TICKER', usd_krw=1000.0)
    assert price == 25000.0
    assert source == "네이버 금융"
