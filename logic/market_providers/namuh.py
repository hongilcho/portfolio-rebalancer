"""Quote adapter for the existing broker client and its token/throttle policy."""


class NamuhQuotes:
    def __init__(self, client):
        self.client = client

    def exchange_rate(self):
        rate = self.client.fetch_exchange_rate('USD')
        return round(rate, 2) if rate is not None and rate > 0 else None

    def stock(self, ticker, market):
        price = self.client.fetch_current_price(ticker, market=market)
        return price if price is not None and price > 0 else None

    def gold(self):
        price = self.client.fetch_gold_price('M04020000')
        return price if price is not None and price > 0 else None
