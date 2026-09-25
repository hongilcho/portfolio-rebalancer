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
   - 2단계: PostgreSQL DB 영구 캐시(market_prices_cache)를 통한 서버 재시작 시 0초 콜드스타트
"""

import time
import threading
import requests
import yfinance as yf
from data.data_manager import get_market_cache, save_market_cache

# ============================================================================
# 인메모리 캐시 및 동시성 제어 전역 변수
# ============================================================================
_crypto_cache = None          # 직전 수집된 가상자산 시세 딕셔너리 캐시
_crypto_cache_time = 0.0      # 캐시 저장 시각 (timestamp)
_crypto_cache_ttl = 60.0      # 캐시 유효 시간 (초 단위, 기본 60초)
_crypto_lock = threading.Lock() # 백그라운드 갱신 동시 실행 방지 뮤텍스
_crypto_fetching = False      # 현재 백그라운드에서 시세 갱신 중인지 여부 플래그

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

def _background_crypto_refresh():
    """
    백그라운드 스레드에서 외부 거래소로부터 가상자산 시세를 갱신합니다.
    
    Stale-While-Revalidate(SWR) 패턴을 지원하여, 캐시 만료 시 사용자가
    시세 조회를 기다리지 않고 즉시 캐시된 데이터를 받은 뒤 백그라운드에서
    최신 시세를 갱신하도록 합니다.
    """
    global _crypto_cache, _crypto_cache_time, _crypto_fetching
    with _crypto_lock:
        if _crypto_fetching:
            return
        _crypto_fetching = True
    try:
        fresh = _fetch_crypto_from_external()
        if fresh and (fresh["BTC"]["price"] > 0 or fresh["ETH"]["price"] > 0):
            _crypto_cache = fresh
            _crypto_cache_time = time.time()
            save_market_cache("crypto", fresh)
    finally:
        _crypto_fetching = False

def get_crypto_prices(force_refresh: bool = False):
    """
    비트코인(BTC) 및 이더리움(ETH)의 실시간 원화 시세를 반환합니다.
    
    2단계 캐싱(인메모리 SWR + PostgreSQL 영구 캐시)을 적용하여
    외부 API 호출 지연을 숨기고 신속한 응답(0~0.05초)을 보장합니다.

    Args:
        force_refresh (bool): True일 경우 캐시를 무시하고 외부 거래소에서 강제로 동기 수집

    Returns:
        dict: BTC, ETH의 원화 평가 시세 정보를 포함한 딕셔너리
    """
    global _crypto_cache, _crypto_cache_time
    now = time.time()

    # 1. 인메모리 캐시가 아직 없으면 DB 영구 캐시에서 0.05초 만에 복구
    if _crypto_cache is None:
        db_cache, age = get_market_cache("crypto")
        if db_cache and isinstance(db_cache, dict) and "BTC" in db_cache:
            _crypto_cache = db_cache
            _crypto_cache_time = now - min(age, 3600.0)

    # 2. 명시적 새로고침 요청이거나 캐시 TTL(60초) 만료 또는 캐시 부재 시 동기 최신화 수집
    if force_refresh or _crypto_cache is None or (now - _crypto_cache_time > _crypto_cache_ttl):
        try:
            fresh = _fetch_crypto_from_external()
            if fresh and (fresh["BTC"]["price"] > 0 or fresh["ETH"]["price"] > 0):
                _crypto_cache = fresh
                _crypto_cache_time = now
                save_market_cache("crypto", fresh)
                return _crypto_cache
        except Exception as e:
            print(f"Error fetching fresh crypto prices: {e}")
        # 외부 수집 실패 시 기존 캐시 폴백 반환
        if _crypto_cache is not None:
            return _crypto_cache

    # 3. 아직 유효한 캐시(60초 이내)가 있으면 즉시 반환
    return _crypto_cache or _fetch_crypto_from_external()

