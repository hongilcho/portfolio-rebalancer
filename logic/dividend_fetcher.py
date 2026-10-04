"""
실제 공시 배당금(분배금) 수집 및 단가 조정 모듈 (Dividend Fetcher)
=================================================================
미국 ETF(SGOV 등) 및 국내 ETF(KODEX 머니마켓액티브 등)의 실제 거래소 공시 배당 이력을
yfinance로부터 수집하여 PostgreSQL market_cache 및 인메모리에 24시간 캐싱하고,
배당락일 당시 보유 수량으로 세후 배당을 계산합니다. 매입단가는 보존합니다.
"""

import time
import pandas as pd
from typing import List, Dict, Any, Optional
import yfinance as yf

from data.data_manager import get_market_cache, save_market_cache
from logic.dividend_calculator import (
    dividend_lookup_key, calculate_holding_dividends,
    get_dividend_tax_rate, calculate_holding_dividends_from_history,
)

from logic.refreshing_cache import RefreshingCache
import threading

_dividend_memory_cache = {}  # one cache per market/ticker, including empty lists
_dividend_lock = threading.Lock()
_dividend_request = threading.local()
CACHE_TTL = 86400.0


def begin_dividend_request(force=False):
    _dividend_request.force = force
    _dividend_request.statuses = {}


def get_dividend_status():
    statuses = list(getattr(_dividend_request, "statuses", {}).values())
    times = [s["updated_at"] for s in statuses if s["updated_at"]]
    return {"updated_at": min(times) if times else None,
            "stale": any(s["stale"] for s in statuses),
            "refreshing": any(s["refreshing"] for s in statuses),
            "refresh_failed": any(s["refresh_failed"] for s in statuses)}


def _get_dividend_cache(clean_ticker, market):
    """Create a lazy cache without doing DB or external provider IO."""
    key = f"div_{market}_{clean_ticker}"

    def load():
        value, age = get_market_cache(key)
        return (value, age) if isinstance(value, list) else (None, 0)

    def fetch():
        sym = clean_ticker
        if market == "KR" and not sym.endswith((".KS", ".KQ")):
            sym += ".KS"
        divs = yf.Ticker(sym).dividends
        records = []
        if divs is not None:
            for dt, amt in divs.items():
                if not pd.isna(amt) and amt > 0:
                    records.append({"date": dt.strftime("%Y-%m-%d"), "amount": round(float(amt), 4)})
        records.sort(key=lambda x: x["date"])
        if not records and cache.value:
            # yfinance can return an empty series after an upstream failure.
            # Previously recorded dividends must not silently disappear.
            raise RuntimeError('Empty dividend response would erase known history')
        save_market_cache(key, records)
        return records

    with _dividend_lock:
        cache = _dividend_memory_cache.setdefault(key, RefreshingCache(CACHE_TTL, load, fetch))
    return cache


def prepare_dividend_cache(batch_data):
    """Restore held tickers from the existing dashboard SQL round trip.

    Only initialise unloaded caches. A later DB snapshot must never overwrite
    an in-flight refresh or a newer memory value. Missing rows remain unknown,
    rather than being seeded as a verified empty dividend history.
    """
    if 'dividend_cache' not in batch_data:
        return  # Older callers/test fixtures retain the lazy loader.
    rows = batch_data['dividend_cache']
    assets = {str(a['id']): a for a in batch_data.get('assets', [])}
    for holding in batch_data.get('holdings', []):
        asset = assets.get(str(holding['asset_id']), {})
        ticker = (asset.get('ticker') or '').strip().upper()
        if (not ticker or ticker in ('없음', '-', 'M04020000')
                or asset.get('is_deposit') or '금' in asset.get('name', '')):
            continue
        market = asset.get('market', 'KR')
        cache = _get_dividend_cache(ticker, market)
        row = rows.get(f'div_{market}_{ticker}')
        with cache.condition:
            if cache.loaded or cache.refreshing:
                continue
            if row and isinstance(row.get('data'), list):
                cache.seed(row['data'], time.time() - max(0, float(row.get('age_seconds') or 0)))
            else:
                # This SQL snapshot already checked the key; avoid another SELECT.
                # With value=None, the existing cold/forced fetch semantics apply.
                cache.loaded = True


def fetch_dividend_history(ticker: str, market: str) -> List[Dict[str, Any]]:
    clean_ticker = (ticker or "").strip().upper()
    if not clean_ticker or clean_ticker in ("없음", "-", "M04020000"):
        return []
    key = f"div_{market}_{clean_ticker}"
    cache = _get_dividend_cache(clean_ticker, market)
    try:
        force = getattr(_dividend_request, "force", False) and key not in getattr(_dividend_request, "statuses", {})
        records, status = cache.get(force=force)
    except RuntimeError:
        if getattr(_dividend_request, "force", False):
            raise
        # No history available: label unavailable, do not persist a guessed zero.
        records, status = [], cache.status()
    _dividend_request.statuses = getattr(_dividend_request, "statuses", {})
    _dividend_request.statuses[key] = status
    return records

def calculate_adjusted_holding_prices(
    holding: dict,
    asset: dict,
    usd_krw: float = 1380.0,
    account_type: str = '',
    trades: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Fetch the cached history, then calculate dividends without provider IO."""
    key = dividend_lookup_key(asset)
    records = fetch_dividend_history(*key) if key else []
    return calculate_holding_dividends(
        holding, asset, usd_krw, account_type=account_type,
        trades=trades, dividend_records=records,
    )
