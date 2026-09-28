"""
실제 공시 배당금(분배금) 수집 및 단가 조정 모듈 (Dividend Fetcher)
=================================================================
미국 ETF(SGOV 등) 및 국내 ETF(KODEX 머니마켓액티브 등)의 실제 거래소 공시 배당 이력을
yfinance로부터 수집하여 PostgreSQL market_cache 및 인메모리에 24시간 캐싱하고,
보유 기간(first_buy_date) 이후 발생한 실제 배당락 금액만큼 매입단가를 차감(Adjusted Cost Basis)합니다.
"""

import time
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import yfinance as yf

from data.data_manager import get_market_cache, save_market_cache

_dividend_memory_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
CACHE_TTL = 86400.0  # 24시간 캐시

def fetch_dividend_history(ticker: str, market: str) -> List[Dict[str, Any]]:
    """
    종목의 거래소 공식 배당/분배금 이력을 수집하여 반환합니다.
    (메모리 캐시 -> PostgreSQL market_cache -> yfinance 순으로 조회)
    """
    clean_ticker = (ticker or '').strip().upper()
    if not clean_ticker or clean_ticker in ['없음', '-', 'M04020000']:
        return []

    cache_key = f"div_{market}_{clean_ticker}"
    now = time.time()

    # 1. 인메모리 캐시 확인
    if cache_key in _dividend_memory_cache:
        cached_time, records = _dividend_memory_cache[cache_key]
        if now - cached_time < CACHE_TTL:
            return records

    # 2. PostgreSQL 지속성 캐시 확인
    try:
        db_cache, age = get_market_cache(cache_key)
        if db_cache and isinstance(db_cache, list) and age < CACHE_TTL:
            _dividend_memory_cache[cache_key] = (now - age, db_cache)
            return db_cache
    except Exception as e:
        print(f"Notice: Failed to read dividend DB cache for {cache_key}: {e}")

    # 3. 외부 API (yfinance) 수집
    sym = clean_ticker
    if market == 'KR':
        if not sym.endswith('.KS') and not sym.endswith('.KQ'):
            sym = f"{sym}.KS"

    try:
        t = yf.Ticker(sym)
        divs = t.dividends
        if divs is None or len(divs) == 0:
            records = []
        else:
            records = []
            for dt, amt in divs.items():
                if pd.isna(amt) or amt <= 0:
                    continue
                dt_str = dt.strftime("%Y-%m-%d")
                records.append({"date": dt_str, "amount": round(float(amt), 4)})
            records.sort(key=lambda x: x["date"])

        # 캐시 저장
        _dividend_memory_cache[cache_key] = (now, records)
        save_market_cache(cache_key, records)
        return records
    except Exception as e:
        print(f"Notice: Failed to fetch dividends from yfinance for {sym}: {e}")
        # 실패 시 기존 만료된 DB 캐시라도 있으면 반환
        try:
            old_cache, _ = get_market_cache(cache_key)
            if old_cache and isinstance(old_cache, list):
                return old_cache
        except Exception:
            pass
        return []

def get_dividend_tax_rate(account_type: str, market: str) -> float:
    """
    계좌 유형 및 시장 구분에 따른 배당소득세 원천징수세율을 반환합니다.
    - 절세/비과세 계좌 (ISA, IRP, 연금저축): 0.0% (비과세 또는 인출 시까지 과세이연)
    - 일반 과세 계좌 (종합매매, 위탁, 일반, CMA 등):
      - 국내 시장(KR): 15.4% (배당소득세 14% + 지방소득세 1.4%)
      - 미국 시장(US): 15.0% (한미 조세협약 미국 원천징수 15.0%)
    """
    acc_clean = (account_type or '').strip().upper()
    if any(k in acc_clean for k in ['ISA', 'IRP', '연금', 'PENSION']):
        return 0.0
    if market == 'US':
        return 0.150
    return 0.154

def calculate_adjusted_holding_prices(holding: dict, asset: dict, usd_krw: float = 1380.0, account_type: str = '') -> Dict[str, Any]:
    """
    개별 보유 종목의 배당금 단가 차감(Adjusted Cost Basis)을 계산합니다.
    
    자산에 `is_dividend_cost_deduct`가 활성화되어 있으면,
    보유 시작일(`first_buy_date`) 이후 발생한 실제 공시 배당금에서
    계좌 유형별 배당소득세(일반계좌 15.4%/미국 15%, 절세계좌 0%)를 원천징수한
    '세후 실지급 배당금'을 원래 매입단가(`original_avg_price`)에서 차감한
    유효 매입단가(`avg_price`)를 반환합니다.
    """
    is_deduct = bool(asset.get('is_dividend_cost_deduct', False))
    market = asset.get('market', 'KR')
    is_us = (market == 'US')

    curr_krw = float(holding.get('avg_price') or 0.0)
    curr_usd = float(holding.get('avg_price_usd') or 0.0)
    orig_krw = float(holding.get('original_avg_price') or curr_krw)
    orig_usd = float(holding.get('original_avg_price_usd') or curr_usd)
    first_buy_date = str(holding.get('first_buy_date') or '').strip()
    buy_fx_rate = float(holding.get('buy_fx_rate') or 0.0)
    
    if buy_fx_rate <= 0:
        if orig_usd > 0 and orig_krw > 0:
            buy_fx_rate = round(orig_krw / orig_usd, 2)
        else:
            buy_fx_rate = usd_krw

    # 계좌 유형 및 세율 결정
    effective_acc_type = holding.get('account_type') or account_type or ''
    tax_rate = get_dividend_tax_rate(effective_acc_type, market)

    if not is_deduct:
        return {
            "avg_price": curr_krw,
            "avg_price_usd": curr_usd,
            "original_avg_price": curr_krw,
            "original_avg_price_usd": curr_usd,
            "cumulative_dividend": 0.0,
            "gross_cumulative_dividend": 0.0,
            "tax_rate": tax_rate,
            "tax_amount": 0.0,
            "is_tax_deducted": False,
            "dividend_count": 0,
            "first_buy_date": first_buy_date,
            "is_dividend_cost_deduct": False,
            "buy_fx_rate": buy_fx_rate,
            "account_type": effective_acc_type
        }

    ticker = asset.get('ticker', '')
    div_records = fetch_dividend_history(ticker, market)

    # first_buy_date 이후의 배당만 필터링
    if first_buy_date:
        qualifying = [d for d in div_records if d['date'] >= first_buy_date]
    else:
        qualifying = []

    gross_cum_div = sum(d['amount'] for d in qualifying)
    tax_amount = round(gross_cum_div * tax_rate, 4 if is_us else 1)
    net_cum_div = max(0.0, gross_cum_div - tax_amount)

    # 수동 배당금 보정이 있는 경우 우선 반영
    manual_override = holding.get('manual_dividend_override')
    if manual_override is not None and float(manual_override) >= 0:
        cum_div = float(manual_override)
    else:
        cum_div = net_cum_div

    if is_us:
        adjusted_usd = max(0.01, orig_usd - cum_div) if orig_usd > 0 else 0.0
        adjusted_krw = round(adjusted_usd * buy_fx_rate, 2)
    else:
        adjusted_krw = max(1.0, orig_krw - cum_div) if orig_krw > 0 else 0.0
        adjusted_usd = round(adjusted_krw / usd_krw, 2) if usd_krw > 0 else 0.0

    return {
        "avg_price": adjusted_krw,
        "avg_price_usd": round(adjusted_usd, 2),
        "original_avg_price": orig_krw,
        "original_avg_price_usd": round(orig_usd, 2),
        "cumulative_dividend": round(cum_div, 4 if is_us else 1),
        "gross_cumulative_dividend": round(gross_cum_div, 4 if is_us else 1),
        "tax_rate": tax_rate,
        "tax_amount": round(tax_amount, 4 if is_us else 1),
        "is_tax_deducted": tax_rate > 0,
        "dividend_count": len(qualifying),
        "first_buy_date": first_buy_date,
        "is_dividend_cost_deduct": True,
        "buy_fx_rate": buy_fx_rate,
        "account_type": effective_acc_type
    }
