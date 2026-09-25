import time
import threading
import requests
import yfinance as yf
from datetime import datetime

_crypto_cache = None
_crypto_cache_time = 0.0
_crypto_cache_ttl = 60.0  # 1분 캐시
_crypto_lock = threading.Lock()

def get_crypto_prices(force_refresh: bool = False):
    """
    비트코인(BTC) 및 이더리움(ETH) 실시간 원화 시세 수집 (인메모리 캐싱 지원)
    1순위: 업비트(Upbit) Public API
    2순위: 빗썸(Bithumb) Public API
    3순위: yfinance (BTC-KRW, ETH-KRW)
    """
    global _crypto_cache, _crypto_cache_time
    now = time.time()
    if not force_refresh and _crypto_cache is not None and (now - _crypto_cache_time < _crypto_cache_ttl):
        return _crypto_cache

    with _crypto_lock:
        if not force_refresh and _crypto_cache is not None and (time.time() - _crypto_cache_time < _crypto_cache_ttl):
            return _crypto_cache

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
        res = requests.get(url, headers=headers, timeout=5)
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
                _crypto_cache = prices
                _crypto_cache_time = time.time()
                return prices
    except Exception as e:
        print(f"Upbit API error: {e}")

    # 2. 빗썸 (Bithumb) API 폴백
    try:
        for sym in ["BTC", "ETH"]:
            if prices[sym]["price"] <= 0:
                b_url = f"https://api.bithumb.com/public/ticker/{sym}_KRW"
                b_res = requests.get(b_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
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
            _crypto_cache = prices
            _crypto_cache_time = time.time()
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

    if prices["BTC"]["price"] > 0 or prices["ETH"]["price"] > 0:
        _crypto_cache = prices
        _crypto_cache_time = time.time()
    return prices
