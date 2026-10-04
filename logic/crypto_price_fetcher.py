"""
가상자산(암호화폐) 실시간 원화 시세 수집 모듈
=============================================
비트코인(BTC), 이더리움(ETH) 등 가상자산의 원화 실시간 시세를 수집하고 캐싱합니다.

주요 특징:
1. 다중 거래소 폴백 체인:
   - 1차: 업비트(Upbit) Ticker API (초고속, 국내 기준가)
   - 2차: 빗썸(Bithumb) Public Ticker API (국내 2위 거래소)
   - 3차: yfinance (글로벌 시세 기반 KRW 환산 폴백)
2. 2단계 캐싱 아키텍처:
   - 1단계: 60초 인메모리 캐시 (SWR: Stale-While-Revalidate 백그라운드 갱신)
   - 2단계: PostgreSQL DB 영구 캐시(market_cache)를 통한 서버 재시작 시 캐시 복원
"""

import threading
import yfinance as yf
from logic.market_providers.http import quote_http_client
from logic.market_providers.crypto import UpbitQuotes, BithumbQuotes
from logic.market_providers.yahoo import YahooQuotes
from data.data_manager import get_market_cache, save_market_cache

# ============================================================================
# 인메모리 캐시 및 동시성 제어 전역 변수
# ============================================================================
def _http_get(url, headers=None, timeout=3):
    return quote_http_client.get(url, headers=headers, timeout=timeout)


def _fetch_crypto_from_external() -> dict:
    """
    외부 거래소 API를 순차적으로 호출하여 가상자산 실시간 시세를 수집합니다.
    
    Returns:
        dict: BTC, ETH의 원화 시세, 24시간 변동률, 고가, 저가, 전일종가, 수집처 정보를 담은 딕셔너리
    """
    prices = {
        "BTC": {
            "symbol": "BTC",
            "name": "비트코인",
            "price": 0.0,
            "change_24h_pct": 0.0,
            "high_24h": 0.0,
            "low_24h": 0.0,
            "prev_close": 0.0,
            "source": "기본값"
        },
        "ETH": {
            "symbol": "ETH",
            "name": "이더리움",
            "price": 0.0,
            "change_24h_pct": 0.0,
            "high_24h": 0.0,
            "low_24h": 0.0,
            "prev_close": 0.0,
            "source": "기본값"
        }
    }

    for provider, label in ((UpbitQuotes(_http_get), 'Upbit API'),
                            (BithumbQuotes(_http_get), 'Bithumb API')):
        try:
            provider.fill(prices)
            if prices['BTC']['price'] > 0 and prices['ETH']['price'] > 0:
                return prices
        except Exception as error:
            print(f'{label} error: {error}')

    yahoo = YahooQuotes(yf.Ticker)
    for symbol in ('BTC', 'ETH'):
        if prices[symbol]['price'] <= 0:
            try:
                quote = yahoo.crypto(symbol)
                if quote is not None:
                    prices[symbol] = quote
            except Exception as error:
                print(f'yfinance crypto error for {symbol}: {error}')
    return prices


def _load_crypto_snapshot():
    value, age = get_market_cache("crypto")
    if not isinstance(value, dict) or any(float(value.get(sym, {}).get("price", 0)) <= 0 for sym in ("BTC", "ETH")):
        return None, 0
    return value, age


def _fetch_crypto_snapshot():
    value = _fetch_crypto_from_external()
    if not value or any(float(value.get(sym, {}).get("price", 0)) <= 0 for sym in ("BTC", "ETH")):
        raise RuntimeError("Incomplete crypto quotes")
    save_market_cache("crypto", value)
    return value


from logic.refreshing_cache import RefreshingCache
_crypto_snapshots = RefreshingCache(60, _load_crypto_snapshot, _fetch_crypto_snapshot)
_crypto_request = threading.local()


def get_crypto_prices(force_refresh: bool = False):
    value, status = _crypto_snapshots.get(force=force_refresh)
    _crypto_request.status = status
    return value


def get_crypto_status():
    return getattr(_crypto_request, "status", _crypto_snapshots.status())
