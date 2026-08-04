import pytest
import pandas as pd
from price_fetcher import get_us_stock_price
import yfinance as yf

def test_debug(mocker):
    mock_ticker = mocker.MagicMock()
    df = pd.DataFrame({'Close': [150.0, 150.5]})
    mock_ticker.history.return_value = df
    type(mock_ticker).fast_info = mocker.PropertyMock(side_effect=AttributeError)
    mocker.patch('yfinance.Ticker', return_value=mock_ticker)
    
    ticker = yf.Ticker('AAPL')
    hist = ticker.history(period="5d").dropna(subset=['Close'])
    print("HIST:")
    print(hist)
    print("HIST TYPE:", type(hist))
    if not isinstance(hist, mocker.MagicMock):
        print("ILOC -1:", hist['Close'].iloc[-1])
    
if __name__ == '__main__':
    pytest.main(['-s', 'debug_test.py'])
