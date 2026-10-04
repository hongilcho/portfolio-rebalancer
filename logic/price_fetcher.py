"""Quote fallback order, currency conversion and parallel asset collection.

Provider HTTP/SDK parsing lives in logic.market_providers. Public function
signatures, sources, defaults and the domestic batch scheduling stay stable.
"""
import math
import concurrent.futures
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional

import yfinance as yf
from data.nh_api import nh_api_client
from logic.market_providers.http import quote_http_client
from logic.market_providers.naver import NaverQuotes
from logic.market_providers.namuh import NamuhQuotes
from logic.market_providers.yahoo import YahooQuotes
from logic.market_providers.sources import QuoteSources

# Shared across requests, including metadata learned by successful discovery.
_us_ticker_suffix_cache: Dict[str, str] = {
    'VT': 'VT', 'PDBC': 'PDBC.O', 'SLYV': 'SLYV.K',
}


def _get_http_session():
    return quote_http_client.session()


def _http_get(url: str, headers: Optional[dict] = None, timeout: float = 2.0):
    return quote_http_client.get(url, headers=headers, timeout=timeout)


def _sources():
    # Resolve dependencies at call time so tests can replace them explicitly.
    return QuoteSources(
        NaverQuotes(_http_get, _us_ticker_suffix_cache),
        NamuhQuotes(nh_api_client), YahooQuotes(yf.Ticker),
    )


def _first_quote(candidates):
    """Try ordered sources; an unavailable source must not prevent fallback."""
    for fetch, source in candidates:
        try:
            price = fetch()
            if price is not None:
                return price, source
        except Exception:
            pass
    return None, ''


def get_exchange_rate_usd_krw() -> Tuple[float, str]:
    sources = _sources()
    rate, source = _first_quote([
        (sources.naver.exchange_rate, '네이버 금융'),
        (sources.namuh.exchange_rate, 'Namuh API'),
        (sources.yahoo.exchange_rate, 'yfinance'),
    ])
    return (rate, source) if rate is not None else (1380.0, '기본값(기본 1380원)')


def get_kr_stock_price(ticker_code: str) -> Tuple[float | None, str]:
    sources = _sources()
    price, source = _first_quote([
        (lambda: sources.naver.kr_stock(ticker_code), '네이버 금융'),
        (lambda: sources.naver.kr_stock(ticker_code, mobile=True), '네이버 금융'),
        (lambda: sources.namuh.stock(ticker_code, 'KR'), 'NH API'),
    ])
    if price is not None:
        return price, source
    try:
        price = sources.yahoo.stock(ticker_code, 'KR')
        if price is not None:
            return price, 'yfinance'
    except Exception as error:
        return None, f'yfinance 오류: {error}'
    return None, '시세를 찾을 수 없음'


def fetch_kr_stocks_batch(ticker_codes: List[str]) -> Dict[str, float]:
    try:
        return _sources().naver.kr_batch(ticker_codes)
    except Exception as error:
        print(f'Notice: Naver batch stock fetch error: {error}')
        return {}


def get_krx_gold_price(usd_krw: float = 1380.0) -> Tuple[float, str]:
    sources = _sources()
    price, source = _first_quote([
        (sources.namuh.gold, 'NH API'),
        (sources.naver.gold, '네이버 금융'),
        (lambda: sources.naver.gold(webpage=True), '네이버 금융'),
    ])
    if price is not None:
        return price, source
    try:
        ounces = sources.yahoo.gold()
        if ounces is not None:
            rate = float(usd_krw if usd_krw and usd_krw > 0 else 1380.0)
            return round(ounces * rate / 31.1034768, 0), 'COMEX 금선물'
    except Exception:
        pass
    return 201620.0, '기본값'


def get_us_stock_price(ticker_symbol: str, usd_krw: float = 1380.0) -> Tuple[float | None, str]:
    rate = float(usd_krw if usd_krw and usd_krw > 0 else 1380.0)
    sources = _sources()
    price, source = _first_quote([
        (lambda: sources.naver.us_stock(ticker_symbol), '네이버 금융'),
        (lambda: sources.namuh.stock(ticker_symbol, 'US'), 'NH API'),
    ])
    if price is not None:
        return round(price * rate, 2), source
    try:
        price = sources.yahoo.stock(ticker_symbol, 'US')
        if price is not None:
            return round(price * rate, 2), 'yfinance'
    except Exception as error:
        return None, f'yfinance 오류: {error}'
    return None, '시세를 찾을 수 없음'


def calculate_deposit_price(asset: dict) -> Tuple[float, int, float, float]:
    """
    정기예금 자산의 일할(Daily) 세후 누적이자를 계산하여 현재 평가액을 산출합니다.
    
    계산 공식:
      - 경과일수: min(오늘, 만기일) - 가입일 (만기 이후 추가 이자는 미발생)
      - 세전이자 = 원금 * (연이율 / 100) * (경과일수 / 365)
      - 이자소득세 = floor(세전이자 * (소득세율 / 100))  [기본 세율: 15.4%]
      - 세후이자 = 세전이자 - 이자소득세
      - 현재가(평가액) = 원금 + 세후이자
      
    Args:
        asset (dict): 정기예금 자산 메타데이터
                      (deposit_principal, interest_rate, start_date, maturity_date, tax_rate 등)
                      
    Returns:
        Tuple[float, int, float, float]: 
            (세후 평가금액, 경과일수, 세전이자, 세후이자)
    """
    principal = float(asset.get('deposit_principal') or 0.0)
    rate = float(asset.get('interest_rate') or 0.0)
    tax_rate = float(asset.get('tax_rate') if asset.get('tax_rate') is not None else 15.4)
    start_date_str = str(asset.get('start_date') or '').strip()
    maturity_date_str = str(asset.get('maturity_date') or '').strip()

    if principal <= 0:
        return 0.0, 0, 0.0, 0.0
    if not start_date_str:
        return principal, 0, 0.0, 0.0

    try:
        start_date = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
    except Exception:
        return principal, 0, 0.0, 0.0

    today = datetime.now().date()

    maturity_date = None
    if maturity_date_str:
        try:
            maturity_date = datetime.strptime(maturity_date_str[:10], "%Y-%m-%d").date()
        except Exception:
            pass

    if today < start_date:
        accrued_days = 0
    elif maturity_date and today > maturity_date:
        accrued_days = max(0, (maturity_date - start_date).days)
    else:
        accrued_days = max(0, (today - start_date).days)

    gross_interest = principal * (rate / 100.0) * (accrued_days / 365.0)
    tax_amount = math.floor(gross_interest * (tax_rate / 100.0))
    net_interest = gross_interest - tax_amount

    return round(principal + net_interest, 0), accrued_days, gross_interest, net_interest

def _fetch_single_asset_price(asset: dict, usd_krw: float, now_str: str, kr_batch_prices: Optional[dict] = None) -> dict:
    """
    개별 자산의 시장 유형(예금, 금현물, 국내주식, 미국주식)에 따라 적절한 수집기를 호출하고,
    원화 평가 시세와 메타데이터가 포함된 자산 가격 딕셔너리를 반환합니다.

    Args:
        asset (dict): 자산 정보 딕셔너리
        usd_krw (float): 현재 적용 환율
        now_str (str): 시세 수집 시각 문자열 ("YYYY-MM-DD HH:MM:SS")
        kr_batch_prices (dict, optional): 사전 수집된 국내 주식 배치 시세 맵

    Returns:
        dict: 원화/외화 시세, 수집 상태, 예금 부가정보 등이 병합된 자산 가격 딕셔너리
    """
    is_deposit = bool(asset.get('is_deposit', False))
    market = asset.get('market')
    ticker = (asset.get('ticker') or '').strip()
    
    if is_deposit:
        price_krw, accrued_days, gross_int, net_int = calculate_deposit_price(asset)
        raw_price = price_krw
        price_usd = price_krw / usd_krw if usd_krw else 0.0
        rate = float(asset.get('interest_rate') or 0.0)
        status = f"정상 (예금 일할이자 연 {rate}%, {accrued_days}일 경과)"
    elif not ticker or ticker == '없음' or ticker == '-':
        if '금' in asset.get('name', '') or 'Gold' in asset.get('name', ''):
            raw_price, source = get_krx_gold_price(usd_krw)
            if raw_price is not None:
                price_krw = raw_price
                price_usd = raw_price / usd_krw if usd_krw else 0
                status = f"정상 ({source})"
            else:
                price_krw = 0.0
                price_usd = 0.0
                status = f"오류: {source}"
        else:
            raw_price = 0.0
            price_krw = 0.0
            price_usd = 0.0
            status = "수동 입력 필요 (Ticker 없음)"
    elif market == 'KR':
        if ticker == 'M04020000' or '금' in asset.get('name', ''):
            raw_price, source = get_krx_gold_price(usd_krw)
        elif kr_batch_prices and ticker in kr_batch_prices:
            raw_price = kr_batch_prices[ticker]
            source = "네이버 금융"
        else:
            raw_price, source = get_kr_stock_price(ticker)
            
        if raw_price is not None:
            price_krw = raw_price
            price_usd = raw_price / usd_krw if usd_krw else 0
            status = f"정상 ({source})"
        else:
            price_krw = 0.0
            price_usd = 0.0
            status = f"오류: {source}"
    else: # US
        raw_price, source = get_us_stock_price(ticker, usd_krw)
        if raw_price is not None:
            price_krw = raw_price
            price_usd = raw_price / usd_krw if usd_krw else 0
            status = f"정상 ({source})"
        else:
            price_usd = 0.0
            price_krw = 0.0
            status = f"오류: {source}"
            
    return {
        "id": asset['id'],
        "name": asset['name'],
        "ticker": asset['ticker'],
        "market": asset['market'],
        "target_weight": asset['target_weight'],
        "allowed_accounts": asset.get('allowed_accounts', []),
        "price_native": raw_price if raw_price else 0.0,
        "price_krw": price_krw,
        "price_usd": round(price_usd, 2) if price_usd else 0.0,
        "usd_krw": usd_krw,
        "status": status,
        "updated_at": now_str,
        "is_deposit": is_deposit,
        "deposit_principal": float(asset.get('deposit_principal') or 0.0),
        "interest_rate": float(asset.get('interest_rate') or 0.0),
        "start_date": asset.get('start_date', ''),
        "maturity_date": asset.get('maturity_date', ''),
        "early_termination_rate": float(asset.get('early_termination_rate') or 0.0),
        "tax_rate": float(asset.get('tax_rate') if asset.get('tax_rate') is not None else 15.4),
        "lock_rebalance_sell": bool(asset.get('lock_rebalance_sell', True) if asset.get('lock_rebalance_sell') is not None else True)
    }

def fetch_asset_prices(assets: list, usd_krw: float = None) -> Tuple[list, float]:
    """
    포트폴리오에 등록된 전체 자산 목록의 실시간 시세 및 원화 환산 가격을
    국내 주식 배치 API 및 멀티스레드 병렬 실행으로 수집합니다.

    Args:
        assets (list): 조회할 자산 정보 딕셔너리 리스트
        usd_krw (float, optional): 적용할 USD/KRW 환율. None일 경우 실시간으로 즉시 조회

    Returns:
        Tuple[list, float]: (시세 정보가 보강된 자산 결과 리스트, 적용된 USD/KRW 환율)
    """
    if not assets:
        rate = usd_krw if usd_krw is not None else get_exchange_rate_usd_krw()[0]
        return [], rate

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 국내 주식 티커 목록 추출 (금현물 및 예금 제외)
    kr_tickers = [
        str(a.get('ticker') or '').strip()
        for a in assets
        if a.get('market') == 'KR' and not a.get('is_deposit') and str(a.get('ticker') or '').strip() not in ('M04020000', '없음', '-', '')
    ]

    # 2. 환율 및 국내 주식 배치 선제/동시 수집
    need_rate = (usd_krw is None)
    max_workers = min(12, len(assets) + 2)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        f_rate = executor.submit(get_exchange_rate_usd_krw) if need_rate else None
        f_kr_batch = executor.submit(fetch_kr_stocks_batch, kr_tickers) if kr_tickers else None

        if need_rate and f_rate:
            usd_krw, _ = f_rate.result()
        elif usd_krw is None:
            usd_krw = 1380.0

        # Start US/gold/deposit work before waiting for the domestic batch.
        # Preserve input ordering; domestic assets still reuse the batch result.
        batch_indices = {
            i for i, asset in enumerate(assets)
            if asset.get('market') == 'KR' and not asset.get('is_deposit')
            and str(asset.get('ticker') or '').strip() in kr_tickers
        }
        futures = {
            i: executor.submit(_fetch_single_asset_price, asset, usd_krw, now_str, {})
            for i, asset in enumerate(assets) if i not in batch_indices
        }
        kr_batch_prices = f_kr_batch.result() if f_kr_batch else {}
        for i in batch_indices:
            futures[i] = executor.submit(_fetch_single_asset_price, assets[i], usd_krw, now_str, kr_batch_prices)
        results = [futures[i].result() for i in range(len(assets))]

    return results, usd_krw
