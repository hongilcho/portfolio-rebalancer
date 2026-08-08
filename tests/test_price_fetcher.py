import pytest
from logic.price_fetcher import get_kr_stock_price, get_us_stock_price, get_krx_gold_price, get_exchange_rate_usd_krw

def test_get_us_stock_price(mocker):
    # Mock yfinance Ticker and history
    mock_ticker = mocker.MagicMock()
    mock_hist = mocker.MagicMock()
    
    # Setup mock data for history
    import pandas as pd
    mock_hist.empty = False
    mock_hist.dropna.return_value = mock_hist
    mock_hist['Close'].iloc = [-1, 150.5] # Simple list mock won't work well for pandas iloc, better to mock the entire return
    
    # A safer way to mock the exact pandas behavior:
    df = pd.DataFrame({'Close': [150.0, 150.5]})
    mock_ticker.history.return_value = df
    
    # Disable fast_info for this test by making it None
    mock_ticker.fast_info = None

    mocker.patch('logic.price_fetcher.yf.Ticker', return_value=mock_ticker)
    
    price, err = get_us_stock_price('AAPL')
    assert price == 150.5
    assert err is None

def test_get_us_stock_price_fastinfo(mocker):
    mock_ticker = mocker.MagicMock()
    mock_fast_info = mocker.MagicMock()
    mock_fast_info.last_price = 151.0
    mock_ticker.fast_info = mock_fast_info
    
    mocker.patch('logic.price_fetcher.yf.Ticker', return_value=mock_ticker)
    
    price, err = get_us_stock_price('AAPL')
    assert price == 151.0
    assert err is None

def test_get_exchange_rate(mocker):
    # Mock yfinance to fail, forcing fallback
    mocker.patch('logic.price_fetcher.yf.Ticker', side_effect=Exception("API Error"))
    
    # Mock requests.get for Naver fallback
    mock_response = mocker.MagicMock()
    mock_response.text = 'today<span class="blind">1,350.50</span>'
    mocker.patch('logic.price_fetcher.requests.get', return_value=mock_response)
    
    rate, source = get_exchange_rate_usd_krw()
    assert rate == 1350.5
