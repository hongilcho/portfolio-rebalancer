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
    sync_account_with_api
)
from logic.price_fetcher import get_exchange_rate_usd_krw, fetch_asset_prices
from logic.rebalance_calculator import calculate_rebalancing_plan
from data.nh_api import nh_api_client

class MarketStateService:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.usd_krw: float = 1380.0
        self.rate_source: str = "초기화중"
        self.is_custom_rate: bool = False
        self.price_data: Optional[List[Dict[str, Any]]] = None
        self.last_price_fetch_time: float = 0.0
        self.cache_ttl_seconds: float = 60.0

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance.refresh_exchange_rate()
            return cls._instance

    def refresh_exchange_rate(self):
        if not self.is_custom_rate:
            rate, source = get_exchange_rate_usd_krw()
            self.usd_krw = float(rate)
            self.rate_source = source
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

    def get_prices(self, force_refresh: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        now = time.time()
        assets = get_all_assets()
        
        if force_refresh or self.price_data is None or (now - self.last_price_fetch_time > self.cache_ttl_seconds):
            if not self.is_custom_rate:
                self.refresh_exchange_rate()
                
            price_results, _ = fetch_asset_prices(assets, self.usd_krw)
            self.price_data = price_results
            self.last_price_fetch_time = now
            
        price_map = {}
        if self.price_data:
            for item in self.price_data:
                price_map[str(item['id'])] = float(item['price_krw'])
                
        return self.price_data or [], price_map

market_service = MarketStateService.get_instance()
