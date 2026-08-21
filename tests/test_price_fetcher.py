import pytest
from logic.price_fetcher import get_kr_stock_price, get_us_stock_price, get_krx_gold_price, get_exchange_rate_usd_krw

def test_get_us_stock_price(mocker):
    # Mock nh_api_client to fail, testing yfinance fallback
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_current_price', return_value=None)
    
    # Mock yfinance Ticker and history
    mock_ticker = mocker.MagicMock()
    
    # Setup mock data for history
    import pandas as pd
    df = pd.DataFrame({'Close': [150.0, 150.5]})
    mock_ticker.history.return_value = df
    mock_ticker.fast_info = None

    mocker.patch('logic.price_fetcher.yf.Ticker', return_value=mock_ticker)
    
    price, source = get_us_stock_price('AAPL', usd_krw=1380.0)
    assert price == 150.5 * 1380.0
    assert source == "yfinance"

def test_get_us_stock_price_fastinfo(mocker):
    mocker.patch('logic.price_fetcher.nh_api_client.fetch_current_price', return_value=None)
    
    mock_ticker = mocker.MagicMock()
    mock_fast_info = mocker.MagicMock()
    mock_fast_info.last_price = 151.0
    mock_ticker.fast_info = mock_fast_info
    
    mocker.patch('logic.price_fetcher.yf.Ticker', return_value=mock_ticker)
    
    price, source = get_us_stock_price('AAPL', usd_krw=1380.0)
    assert price == 151.0 * 1380.0
    assert source == "yfinance"

def test_get_exchange_rate(mocker):
    # Mock yfinance to fail, forcing fallback
    mocker.patch('logic.price_fetcher.yf.Ticker', side_effect=Exception("API Error"))
    
    # Mock requests.get for Naver fallback
    mock_response = mocker.MagicMock()
    mock_response.text = 'today<span class="blind">1,350.50</span>'
    mocker.patch('logic.price_fetcher.requests.get', return_value=mock_response)
    
    rate, source = get_exchange_rate_usd_krw()
    assert rate == 1350.5
