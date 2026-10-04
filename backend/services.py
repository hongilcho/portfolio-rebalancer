"""
시장 상태 및 시세 캐싱 서비스 모듈 (Market State Service)
=========================================================
실시간 환율(USD/KRW) 및 자산별 실시간 시세 데이터를 관리하는 싱글톤(Singleton) 서비스입니다.

주요 특징:
1. 싱글톤 패턴(Singleton): 애플리케이션 전역에서 단일 인스턴스로 시세 상태 공유.
2. 메모리 및 PostgreSQL `market_cache`에 시세를 보관.
3. 만료된 캐시는 즉시 반환하고 백그라운드 갱신. 강제 새로고침과 캐시 부재 시 동기 갱신.
4. 동시성 락(`_fetch_lock`):
   - 여러 요청이 동시에 인입되어도 외부 API 중복 호출을 방지.
"""

import os
import sys
import time
import threading
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from data.data_manager import get_all_assets, get_market_cache, save_market_cache
from logic.price_fetcher import get_exchange_rate_usd_krw, fetch_asset_prices
from logic.refreshing_cache import RefreshingCache

class MarketStateService:
    """
    시장 시세 및 환율 상태를 인메모리와 DB에 2단계로 캐싱하고 동기화하는 서비스 클래스
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.usd_krw: float = 1380.0
        self.rate_source: str = "기본값"
        self.is_custom_rate: bool = False
        self.price_data: Optional[List[Dict[str, Any]]] = None
        self.last_price_fetch_time: float = 0.0
        self.cache_ttl_seconds: float = 300.0  # 5분 캐시
        self._fetch_lock = threading.Lock()
        # Cache IO is deferred until startup or a request, never at import time.
        self._cache = RefreshingCache(300, self._load_snapshot, self._fetch_snapshot)
        self._request = threading.local()

    @classmethod
    def get_instance(cls):
        """싱글톤 인스턴스를 반환합니다. (스레드 안전)"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_snapshot(self):
        prices, age = get_market_cache("prices")
        if not isinstance(prices, list) or not prices:
            return None, 0
        cached_rate, _ = get_market_cache("exchange_rate")
        rate = float(prices[0].get("usd_krw") or (cached_rate or {}).get("usd_krw") or self.usd_krw)
        return {"prices": prices, "usd_krw": rate,
                "rate_source": (cached_rate or {}).get("rate_source", "DB 캐시")}, age

    def _fetch_snapshot(self):
        with self._fetch_lock:
            revision = self._cache.revision
            assets = get_all_assets()
            rate, source = (self.usd_krw, self.rate_source) if self.is_custom_rate else get_exchange_rate_usd_krw()
            if not self.is_custom_rate and (rate <= 0 or str(source).startswith('기본값')):
                raise RuntimeError('Exchange rate provider unavailable')
            prices, _ = fetch_asset_prices(assets, rate)
            if not prices and assets:
                raise RuntimeError("No market prices")
            if any(float(p.get("price_krw") or 0) <= 0 and not p.get("is_deposit") and p.get("ticker") not in ("", "-", "없음") for p in prices):
                raise RuntimeError("Incomplete market prices")
            if revision != self._cache.revision:
                raise RuntimeError('Asset metadata changed during collection')
            self.price_data, self.last_price_fetch_time = prices, time.time()
            self.usd_krw, self.rate_source = rate, source
            save_market_cache("prices", prices)
            save_market_cache("exchange_rate", {"usd_krw": rate, "rate_source": source})
            return {"prices": prices, "usd_krw": rate, "rate_source": source}

    def request_snapshot(self):
        return getattr(self._request, "snapshot", {
            "prices": self.price_data or [], "usd_krw": self.usd_krw, "rate_source": self.rate_source})

    def current_snapshot(self):
        with self._cache.condition:
            return self._cache.value or {
                'prices': self.price_data or [], 'usd_krw': self.usd_krw, 'rate_source': self.rate_source}

    def request_status(self):
        return getattr(self._request, "status", self._cache.status())

    def refresh_exchange_rate(self):
        self.get_prices(force_refresh=True)
        snapshot = self.request_snapshot()
        return snapshot["usd_krw"], snapshot["rate_source"]

    def set_custom_exchange_rate(self, rate: float):
        with self._fetch_lock:
            self.usd_krw = float(rate)
            self.rate_source = "수동입력"
            self.is_custom_rate = True
            self.invalidate_price_cache()

    def reset_custom_exchange_rate(self):
        with self._fetch_lock:
            self.is_custom_rate = False
            self.invalidate_price_cache()

    def invalidate_price_cache(self):
        # Metadata/FX changes require a new compatible valuation, not a stale one.
        self.price_data = None
        self.last_price_fetch_time = 0.0
        with self._cache.condition:
            self._cache.value = None
            self._cache.loaded = True
            self._cache.invalidate()

    def warmup(self):
        self.get_prices()

    def get_prices(self, force_refresh: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        snapshot, status = self._cache.get(force=force_refresh)
        self._request.snapshot, self._request.status = snapshot, status
        prices = snapshot["prices"]
        return prices, {str(p["id"]): float(p["price_krw"]) for p in prices}

market_service = MarketStateService.get_instance()
