"""Dated regular closes only. Live quotes, proxies and default prices are forbidden.

Naver's KRX daily chart identifies its exchange explicitly. US daily charts
exclude the separate over-market quote. Yahoo fallback requests raw Close,
never dividend-adjusted Close. Failure of any held position blocks NAV saving.
"""
from datetime import datetime, timedelta, timezone
import math
import re
from urllib.parse import quote
import yfinance as yf
from logic.close_calendar import KST, cutoff, us_session
from logic.market_providers.http import quote_http_client
from logic.price_fetcher import calculate_deposit_price


class CloseUnavailable(ValueError):
    pass


def positive(value):
    number = float(str(value).replace(',', ''))
    if not math.isfinite(number) or number <= 0:
        raise CloseUnavailable('유효한 종가·환율이 없습니다.')
    return number


class ClosingPrices:
    def __init__(self, http_get=None, ticker_factory=None):
        self.get = http_get or quote_http_client.get
        self.ticker = ticker_factory or yf.Ticker

    def json(self, url):
        response = self.get(url, headers={'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://m.stock.naver.com/'}, timeout=8)
        response.raise_for_status()
        return response.json()

    def exchange_rate(self, now):
        info = self.json('https://api.stock.naver.com/marketindex/exchange/FX_USDKRW')['exchangeInfo']
        published = datetime.fromisoformat(info['localTradedAt'])
        # A stale/default rate must not quietly become a closing valuation.
        if published.tzinfo is None or published.astimezone(KST).date() != now.astimezone(KST).date() or not timedelta(0) <= now-published <= timedelta(hours=6):
            raise CloseUnavailable('당일 환율 고시를 확인할 수 없습니다.')
        return {'rate': positive(info['calcPrice'] if info.get('calcPrice') else info['closePrice']),
                'source': '네이버 금융 · 하나은행 고시', 'published_at': published.isoformat(),
                'collected_at': now.isoformat()}

    @staticmethod
    def dated(rows, day, field='localDate'):
        expected = day.strftime('%Y%m%d')
        for row in rows:
            actual = str(row.get(field, ''))[:10].replace('-', '')
            if actual == expected:
                return positive(row['closePrice'])
        raise CloseUnavailable(f'{day} 종가가 아직 제공되지 않았습니다.')

    def naver(self, asset, day, us_day):
        ticker = str(asset.get('ticker', '')).strip().upper()
        if ticker == 'M04020000':
            basic = self.json('https://api.stock.naver.com/marketindex/metals/M04020000')
            published = datetime.fromisoformat(basic['localTradedAt'])
            if published.tzinfo is None or published.astimezone(KST).date() < day:
                raise CloseUnavailable('금현물 종가 날짜를 확인할 수 없습니다.')
            if published.astimezone(KST).date() == day and basic.get('marketStatus') != 'CLOSE':
                raise CloseUnavailable('금현물 정규장이 아직 마감되지 않았습니다.')
            rows = self.json('https://api.stock.naver.com/marketindex/metals/M04020000/prices')
            return self.dated(rows, day, 'localTradedAt')
        if asset['market'] == 'KR':
            if not re.fullmatch(r'[0-9A-Z]{6}', ticker):
                raise CloseUnavailable('국내 종목 코드를 확인해주세요.')
            data = self.json(f'https://api.stock.naver.com/chart/domestic/item/{ticker}?periodType=dayCandle')
            if data.get('code') != ticker or data.get('stockExchangeType') != 'KRX':
                raise CloseUnavailable('KRX 일별 종가 데이터가 아닙니다.')
            return self.dated(data['priceInfos'], day)
        if asset['market'] != 'US':
            raise CloseUnavailable('지원하지 않는 시장입니다.')
        suffix = {'VT': 'VT', 'PDBC': 'PDBC.O', 'SLYV': 'SLYV.K'}.get(ticker, ticker)
        symbol = quote(suffix, safe='')
        rows = self.json(f'https://api.stock.naver.com/chart/foreign/item/{symbol}/day?startDateTime={us_day:%Y%m%d}0000&endDateTime={us_day+timedelta(days=1):%Y%m%d}0000')
        return self.dated(rows, us_day)

    def yahoo(self, asset, day):
        ticker = str(asset.get('ticker', '')).strip().upper()
        symbols = [ticker] if asset['market'] == 'US' else [f'{ticker}.KS', f'{ticker}.KQ']
        for symbol in symbols:
            try:
                bars = self.ticker(symbol).history(start=day.isoformat(), end=(day+timedelta(days=1)).isoformat(),
                    interval='1d', auto_adjust=False, actions=False, prepost=False, timeout=8)
                matches = bars[[d.date() == day for d in bars.index]]
                if len(matches) == 1:
                    return positive(matches.iloc[0]['Close'])
            except Exception:
                continue
        raise CloseUnavailable(f'{ticker} · {day} 정규장 종가를 확인할 수 없습니다.')

    def asset(self, asset, day, fx):
        if asset.get('is_deposit'):
            return {'id': asset['id'], 'price_krw': positive(calculate_deposit_price(asset, day)[0]),
                    'price_date': day.isoformat(), 'source': '평가일 기준 예금 원리금'}
        target = us_session(cutoff(day)) if asset['market'] == 'US' else day
        source = '네이버 금융 · 정규장 일별 종가'
        try:
            price = self.naver(asset, day, target)
        except Exception:
            if asset.get('ticker') == 'M04020000':
                # Gold futures are not a substitute for KRX physical gold.
                raise CloseUnavailable(f'{day} KRX 금현물 종가 수집을 재시도합니다.') from None
            price = self.yahoo(asset, target)
            source = 'Yahoo · 정규장 비수정 종가'
        return {'id': asset['id'], 'ticker': asset.get('ticker'), 'market': asset['market'],
                'price_date': target.isoformat(), 'price_native': price,
                'price_krw': price * fx if asset['market'] == 'US' else price,
                'source': source, 'collected_at': datetime.now(timezone.utc).isoformat()}


def held_assets(batch):
    held = {h['asset_id'] for h in batch['holdings'] if float(h.get('quantity') or 0) > 0}
    return [a for a in batch['assets'] if (a['id'] in held and not a.get('is_deposit')) or
            (a.get('is_deposit') and float(a.get('deposit_principal') or 0) > 0)]
