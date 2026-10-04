"""Public exchange response adapters, preserving partially collected quotes."""


class UpbitQuotes:
    def __init__(self, http_get):
        self.http_get = http_get

    def fill(self, prices):
        response = self.http_get(
            'https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH',
            headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}, timeout=3,
        )
        if response.status_code == 200:
            for item in response.json():
                market = item.get('market', '')
                if market not in ('KRW-BTC', 'KRW-ETH'):
                    continue
                symbol = market[4:]
                prices[symbol] = {
                    'symbol': symbol,
                    'name': '비트코인' if symbol == 'BTC' else '이더리움',
                    'price': float(item.get('trade_price', 0.0)),
                    'change_24h_pct': round(float(item.get('signed_change_rate', 0.0)) * 100, 2),
                    'high_24h': float(item.get('high_price', 0.0)),
                    'low_24h': float(item.get('low_price', 0.0)),
                    'prev_close': float(item.get('prev_closing_price', 0.0)),
                    'source': '업비트 (Upbit)',
                }


class BithumbQuotes:
    def __init__(self, http_get):
        self.http_get = http_get

    def fill(self, prices):
        for symbol in ('BTC', 'ETH'):
            if prices[symbol]['price'] <= 0:
                response = self.http_get(
                    f'https://api.bithumb.com/public/ticker/{symbol}_KRW',
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=3,
                )
                if response.status_code == 200:
                    data = response.json().get('data', {})
                    price = float(data.get('closing_price', 0.0))
                    previous = float(data.get('prev_closing_price', price))
                    change = round((price - previous) / previous * 100, 2) if previous > 0 else 0.0
                    prices[symbol] = {
                        'symbol': symbol,
                        'name': '비트코인' if symbol == 'BTC' else '이더리움',
                        'price': price, 'change_24h_pct': change,
                        'high_24h': float(data.get('max_price', 0.0)),
                        'low_24h': float(data.get('min_price', 0.0)),
                        'prev_close': previous, 'source': '빗썸 (Bithumb)',
                    }
