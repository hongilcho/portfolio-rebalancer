"""Naver quote parsing and US exchange suffix discovery."""
from lxml import html


class NaverQuotes:
    def __init__(self, http_get, suffix_cache):
        self.http_get = http_get
        self.suffix_cache = suffix_cache

    def exchange_rate(self):
        response = self.http_get(
            'https://api.stock.naver.com/marketindex/exchange/FX_USDKRW',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=2,
        )
        if response.status_code == 200:
            info = response.json().get('exchangeInfo', {})
            value = info.get('calcPrice') or info.get('closePrice')
            if value:
                rate = float(str(value).replace(',', '').strip())
                if rate > 500:
                    return round(rate, 2)
        return None

    def kr_stock(self, ticker, mobile=False):
        url = (f'https://m.stock.naver.com/api/stock/{ticker}/basic' if mobile
               else f'https://polling.finance.naver.com/api/realtime/domestic/stock/{ticker}')
        response = self.http_get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
        if response.status_code == 200:
            data = response.json()
            if not mobile:
                rows = data.get('datas', [])
                if not rows:
                    return None
                data = rows[0]
            value = data.get('closePrice') or data.get('nowPrice')
            if value:
                price = float(str(value).replace(',', '').strip())
                if price > 0:
                    return price
        return None

    def kr_batch(self, tickers):
        if not tickers:
            return {}
        response = self.http_get(
            f"https://polling.finance.naver.com/api/realtime/domestic/stock/{','.join(tickers)}",
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=2.5,
        )
        result = {}
        if response.status_code == 200:
            for item in response.json().get('datas', []):
                code = item.get('itemCode')
                value = item.get('closePrice') or item.get('nowPrice')
                if code and value:
                    try:
                        price = float(str(value).replace(',', '').strip())
                        if price > 0:
                            result[code] = price
                    except (ValueError, TypeError):
                        pass
        return result

    def gold(self, webpage=False):
        if webpage:
            response = self.http_get(
                'https://finance.naver.com/marketindex/goldDetail.naver',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=2.5,
            )
            elements = html.fromstring(response.content).xpath(
                '//p[contains(@class, "no_today")]//span[@class="blind"]'
            )
            if elements:
                price = float(elements[0].text_content().replace(',', '').strip())
                if price > 0:
                    return price
        else:
            response = self.http_get(
                'https://api.stock.naver.com/marketindex/metals/M04020000',
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
                timeout=2.5,
            )
            if response.status_code == 200:
                data = response.json()
                value = data.get('closePrice') or data.get('nowPrice')
                if value:
                    price = float(str(value).replace(',', '').strip())
                    if price > 0:
                        return price
        return None

    def _us_candidate(self, symbol):
        response = self.http_get(
            f'https://api.stock.naver.com/stock/{symbol}/basic',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            timeout=2,
        )
        if response.status_code == 200:
            data = response.json()
            value = data.get('closePrice') or data.get('nowPrice')
            if value:
                price = float(str(value).replace(',', '').strip())
                if price > 0:
                    return price
        return None

    def us_stock(self, ticker):
        cached = self.suffix_cache.get(ticker)
        if cached:
            try:
                price = self._us_candidate(cached)
                if price is not None:
                    return price
            except Exception:
                pass

        candidates = [ticker]
        base = ticker.split('.')[0] if '.' in ticker else ticker
        if '.' in ticker:
            candidates.append(base)
        candidates.extend([f'{base}.O', f'{base}.K', f'{base}.N'])
        seen = set()
        for candidate in candidates:
            if candidate in seen or candidate == cached:
                continue
            seen.add(candidate)
            try:
                price = self._us_candidate(candidate)
                if price is not None:
                    self.suffix_cache[ticker] = candidate
                    return price
            except Exception:
                pass
        return None
