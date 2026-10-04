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
   - 2단계: PostgreSQL DB 영구 캐시(market_prices_cache)를 통한 서버 재시작 시 캐시 복원
"""

import time
import threading
import requests
import yfinance as yf
from data.data_manager import get_market_cache, save_market_cache

# ============================================================================
# 인메모리 캐시 및 동시성 제어 전역 변수
# ============================================================================
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

    # 1. 업비트 (Upbit) API 시도
    try:
        url = "https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH"
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            for item in data:
                market = item.get("market", "")
                if market == "KRW-BTC":
                    prices["BTC"] = {
                        "symbol": "BTC",
                        "name": "비트코인",
                        "price": float(item.get("trade_price", 0.0)),
                        "change_24h_pct": round(float(item.get("signed_change_rate", 0.0)) * 100, 2),
                        "high_24h": float(item.get("high_price", 0.0)),
                        "low_24h": float(item.get("low_price", 0.0)),
                        "prev_close": float(item.get("prev_closing_price", 0.0)),
                        "source": "업비트 (Upbit)"
                    }
                elif market == "KRW-ETH":
                    prices["ETH"] = {
                        "symbol": "ETH",
                        "name": "이더리움",
                        "price": float(item.get("trade_price", 0.0)),
                        "change_24h_pct": round(float(item.get("signed_change_rate", 0.0)) * 100, 2),
                        "high_24h": float(item.get("high_price", 0.0)),
                        "low_24h": float(item.get("low_price", 0.0)),
                        "prev_close": float(item.get("prev_closing_price", 0.0)),
                        "source": "업비트 (Upbit)"
                    }
            if prices["BTC"]["price"] > 0 and prices["ETH"]["price"] > 0:
                return prices
    except Exception as e:
        print(f"Upbit API error: {e}")

    # 2. 빗썸 (Bithumb) API 폴백
    try:
        for sym in ["BTC", "ETH"]:
            if prices[sym]["price"] <= 0:
                b_url = f"https://api.bithumb.com/public/ticker/{sym}_KRW"
                b_res = requests.get(b_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
                if b_res.status_code == 200:
                    b_data = b_res.json().get("data", {})
                    curr_p = float(b_data.get("closing_price", 0.0))
                    prev_p = float(b_data.get("prev_closing_price", curr_p))
                    chg_pct = round(((curr_p - prev_p) / prev_p * 100), 2) if prev_p > 0 else 0.0
                    prices[sym] = {
                        "symbol": sym,
                        "name": "비트코인" if sym == "BTC" else "이더리움",
                        "price": curr_p,
                        "change_24h_pct": chg_pct,
                        "high_24h": float(b_data.get("max_price", 0.0)),
                        "low_24h": float(b_data.get("min_price", 0.0)),
                        "prev_close": prev_p,
                        "source": "빗썸 (Bithumb)"
                    }
        if prices["BTC"]["price"] > 0 and prices["ETH"]["price"] > 0:
            return prices
    except Exception as e:
        print(f"Bithumb API error: {e}")

    # 3. yfinance 폴백
    for sym, yf_sym in [("BTC", "BTC-KRW"), ("ETH", "ETH-KRW")]:
        if prices[sym]["price"] <= 0:
            try:
                t = yf.Ticker(yf_sym)
                hist = t.history(period="2d")
                if not hist.empty:
                    curr_p = float(hist["Close"].iloc[-1])
                    prev_p = float(hist["Close"].iloc[-2]) if len(hist) > 1 else curr_p
                    chg_pct = round(((curr_p - prev_p) / prev_p * 100), 2) if prev_p > 0 else 0.0
                    prices[sym] = {
                        "symbol": sym,
                        "name": "비트코인" if sym == "BTC" else "이더리움",
                        "price": curr_p,
                        "change_24h_pct": chg_pct,
                        "high_24h": float(hist["High"].iloc[-1]),
                        "low_24h": float(hist["Low"].iloc[-1]),
                        "prev_close": prev_p,
                        "source": "yfinance"
                    }
            except Exception as e:
                print(f"yfinance crypto error for {sym}: {e}")

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
