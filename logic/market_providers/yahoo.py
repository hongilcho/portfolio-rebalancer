"""Yahoo/yfinance response adapters; currency conversion stays with callers."""
import math

import pandas as pd


class YahooQuotes:
    def __init__(self, ticker_factory):
        self.ticker_factory = ticker_factory

    def exchange_rate(self):
        ticker = self.ticker_factory('KRW=X')
        fast = getattr(ticker.fast_info, 'last_price', None)
        if fast is not None and not math.isnan(fast):
            return round(float(fast), 2)
        history = ticker.history(period='1d')
        if not history.empty:
            return round(float(history['Close'].iloc[-1]), 2)
        return None

    def stock(self, symbol, market):
        symbols = [f'{symbol}.KS', f'{symbol}.KQ'] if market == 'KR' else [symbol]
        for candidate in symbols:
            ticker = self.ticker_factory(candidate)
            fast = getattr(ticker.fast_info, 'last_price', None)
            if fast is not None and not math.isnan(fast):
                return float(fast)
            history = ticker.history(period='1d').dropna(subset=['Close'])
            if not history.empty:
                return float(history['Close'].iloc[-1])
        return None

    def gold(self):
        ticker = self.ticker_factory('GC=F')
        fast = getattr(ticker.fast_info, 'last_price', None)
        if fast is not None and not math.isnan(fast):
            return float(fast)
        history = ticker.history(period='1d').dropna(subset=['Close'])
        if not history.empty:
            price = float(history['Close'].iloc[-1])
            if price > 0:
                return price
        return None

    def crypto(self, symbol):
        ticker = self.ticker_factory(f'{symbol}-KRW')
        history = ticker.history(period='2d')
        if history.empty:
            return None
        price = float(history['Close'].iloc[-1])
        previous = float(history['Close'].iloc[-2]) if len(history) > 1 else price
        change = round((price - previous) / previous * 100, 2) if previous > 0 else 0.0
        return {
            'symbol': symbol,
            'name': '비트코인' if symbol == 'BTC' else '이더리움',
            'price': price, 'change_24h_pct': change,
            'high_24h': float(history['High'].iloc[-1]),
            'low_24h': float(history['Low'].iloc[-1]),
            'prev_close': previous, 'source': 'yfinance',
        }

    def dividends(self, ticker, market):
        symbol = ticker
        if market == 'KR' and not symbol.endswith(('.KS', '.KQ')):
            symbol += '.KS'
        dividends = self.ticker_factory(symbol).dividends
        records = []
        if dividends is not None:
            for date, amount in dividends.items():
                if not pd.isna(amount) and amount > 0:
                    records.append({'date': date.strftime('%Y-%m-%d'),
                                    'amount': round(float(amount), 4)})
        records.sort(key=lambda row: row['date'])
        return records
