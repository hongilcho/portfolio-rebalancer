"""Public Upbit candles only. No trading or exchange-account credentials."""
from datetime import datetime,timezone
from urllib.parse import urlencode

from logic.crypto_history import cutoff,minute_quote


class UpbitHistory:
    def __init__(self,http_get=None,now=None):
        if http_get is None:
            from logic.market_providers.http import quote_http_client
            http_get=quote_http_client.get
        self.http_get=http_get
        self.now=now or (lambda:datetime.now(timezone.utc))

    def prices(self,day,symbols=('BTC','ETH')):
        if cutoff(day)>self.now():raise ValueError('아직 확정되지 않은 평가 시각입니다.')
        result={}
        for symbol in sorted(set(symbols)):
            if symbol not in ('BTC','ETH'):raise ValueError('지원하지 않는 가상자산입니다.')
            query=urlencode(dict(market='KRW-'+symbol,to=cutoff(day).astimezone(timezone.utc).isoformat(),count=1))
            response=self.http_get('https://api.upbit.com/v1/candles/minutes/1?'+query,
                                   headers={'Accept':'application/json'},timeout=5)
            if response.status_code!=200:raise ValueError('과거 분봉 조회에 실패했습니다.')
            result[symbol]=minute_quote(symbol,day,response.json())
        return result
