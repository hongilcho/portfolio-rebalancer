import os
import sys
import time
import threading
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from data.data_manager import (
    init_db, get_all_assets, get_all_accounts, add_account, update_account, delete_account,
    add_asset, update_asset, delete_asset, get_holdings_by_account, get_all_holdings, save_account_holdings,
    execute_trade, get_trade_history, delete_trade,
    ACCOUNT_TYPES, update_account_settings, update_account_priorities, apply_transfer_plan,
    sync_account_with_api, get_market_cache, save_market_cache
)
from logic.price_fetcher import get_exchange_rate_usd_krw, fetch_asset_prices
from logic.rebalance_calculator import calculate_rebalancing_plan
from data.nh_api import nh_api_client

class MarketStateService:
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
        self._is_fetching: bool = False
        
        # 서버 기동 시 DB 영구 캐시에서 0.05초 만에 복구 (Zero Cold-Start)
        self._load_from_db_cache()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_from_db_cache(self):
        """DB에 저장된 마지막 시세 및 환율 스냅샷을 즉시 로드하여 콜드스타트 지연 0초 달성"""
        try:
            cached_prices, age_p = get_market_cache("prices")
            if cached_prices and isinstance(cached_prices, list) and len(cached_prices) > 0:
                self.price_data = cached_prices
                self.last_price_fetch_time = time.time() - min(age_p, 86400.0)

            cached_rate, age_r = get_market_cache("exchange_rate")
            if cached_rate and isinstance(cached_rate, dict):
                self.usd_krw = float(cached_rate.get("usd_krw") or 1380.0)
                self.rate_source = str(cached_rate.get("rate_source") or "DB 캐시")
        except Exception as e:
            print(f"Notice: Failed to load market cache from DB: {e}")

    def refresh_exchange_rate(self):
        if not self.is_custom_rate:
            rate, source = get_exchange_rate_usd_krw()
            self.usd_krw = float(rate)
            self.rate_source = source
            save_market_cache("exchange_rate", {"usd_krw": self.usd_krw, "rate_source": self.rate_source})
        return self.usd_krw, self.rate_source

    def set_custom_exchange_rate(self, rate: float):
        self.usd_krw = float(rate)
        self.rate_source = "수동입력"
        self.is_custom_rate = True
        self.invalidate_price_cache()

    def reset_custom_exchange_rate(self):
        self.is_custom_rate = False
        self.refresh_exchange_rate()
        self.invalidate_price_cache()

    def invalidate_price_cache(self):
        self.price_data = None
        self.last_price_fetch_time = 0.0

    def _do_fetch_prices(self):
        """내부 시세 수집 실행 함수 (_fetch_lock으로 동시 중복 수집 차단 및 DB 캐시 자동 보존)"""
        if self._fetch_lock.acquire(blocking=True):
            try:
                self._is_fetching = True
                assets = get_all_assets()
                if not self.is_custom_rate:
                    self.refresh_exchange_rate()
                price_results, _ = fetch_asset_prices(assets, self.usd_krw)
                if price_results:
                    self.price_data = price_results
                    self.last_price_fetch_time = time.time()
                    # PostgreSQL에 영구 캐시 저장
                    save_market_cache("prices", self.price_data)
                    save_market_cache("exchange_rate", {"usd_krw": self.usd_krw, "rate_source": self.rate_source})
            finally:
                self._is_fetching = False
                self._fetch_lock.release()

    def warmup(self):
        """서버 기동 시 백그라운드에서 캐시 상태를 확인하고 필요한 경우 자동 갱신"""
        now = time.time()
        if self.price_data is None or (now - self.last_price_fetch_time > self.cache_ttl_seconds):
            if not self._is_fetching:
                self._do_fetch_prices()

    def get_prices(self, force_refresh: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        now = time.time()
        
        # 1. 명시적 강제 새로고침인 경우 동기 수집
        if force_refresh:
            self._do_fetch_prices()
        # 2. 인메모리 캐시가 없는 경우 DB 캐시 재확인 후 최후의 수단으로 동기 수집
        elif self.price_data is None:
            self._load_from_db_cache()
            if self.price_data is None:
                self._do_fetch_prices()
        # 3. 캐시 TTL 초과 시 Stale-While-Revalidate (기존 캐시 즉시 0ms 반환 + 백그라운드 갱신)
        elif now - self.last_price_fetch_time > self.cache_ttl_seconds:
            if not self._is_fetching:
                t = threading.Thread(target=self._do_fetch_prices, daemon=True)
                t.start()
            
        price_map = {}
        if self.price_data:
            for item in self.price_data:
                price_map[str(item['id'])] = float(item['price_krw'])
                
        return self.price_data or [], price_map

market_service = MarketStateService.get_instance()
