"""
실시간 시장 시세 및 환율 수집 모듈 (Price Fetcher)
===================================================
국내 주식/ETF, 미국 주식/ETF, KRX 금현물, 정기예금, USD/KRW 환율의
실시간 평가 가격을 다중 소스로부터 신속하고 안정적으로 수집합니다.

시세 수집 전략:
1. 네이버 금융 공식 JSON API (초우선 순위):
   - 국내주식: polling.finance.naver.com 및 m.stock.naver.com
   - 해외주식: api.stock.naver.com (티커 접미사 자동 확장 지원: .O/.K/.N)
   - 환율: api.stock.naver.com FX_USDKRW
   - 평균 응답 지연시간: ~50ms (초고속)
2. NH투자증권 Open API (2차 폴백):
   - 금현물(M04020000) 등 증권사 직접 호가 연동
3. yfinance (3차 폴백):
   - 글로벌 클라우드 환경 및 해외 상장 증권 백업
4. 정기예금:
   - 일할 계산 세후 누적이자(이자소득세 15.4% 원천징수 반영) 공식 적용
"""

import math
import concurrent.futures
from datetime import datetime
from typing import Tuple
import requests
import urllib3
import yfinance as yf
from lxml import html

from data.nh_api import nh_api_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_exchange_rate_usd_krw() -> Tuple[float, str]:
    """
    USD/KRW 실시간 환율을 수집합니다.
    
    수집 우선순위:
      1. 네이버 금융 공식 환율 JSON API (초고속 ~0.05초)
      2. NH투자증권 Open API 환율
      3. yfinance KRW=X (fast_info / history)
      4. 기본값(1380.0원)
      
    Returns:
        Tuple[float, str]: (환율 금액, 수집 출처 문자열)
    """
    # 1. 네이버 금융 공식 환율 JSON API (초고속 0.05초)
    try:
        url_nv = "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url_nv, headers=headers, timeout=2)
        if res.status_code == 200:
            data = res.json()
            info = data.get('exchangeInfo', {})
            val = info.get('calcPrice') or info.get('closePrice')
            if val:
                clean_num = float(str(val).replace(',', '').strip())
                if clean_num > 500:
                    return round(clean_num, 2), "네이버 금융"
    except Exception:
        pass

    # 2. Namuh API 폴백
    try:
        rate = nh_api_client.fetch_exchange_rate("USD")
        if rate is not None and rate > 0:
            return round(rate, 2), "Namuh API"
    except Exception:
        pass

    # 3. yfinance fallback
    try:
        ticker = yf.Ticker("KRW=X")
        fast_rate = getattr(ticker.fast_info, 'last_price', None)
        if fast_rate is not None and not math.isnan(fast_rate):
            return round(float(fast_rate), 2), "yfinance"
        hist = ticker.history(period="1d")
        if not hist.empty:
            rate = float(hist['Close'].iloc[-1])
            return round(rate, 2), "yfinance"
    except Exception:
        pass
        
    return 1380.0, "기본값(기본 1380원)"

def get_kr_stock_price(ticker_code: str) -> Tuple[float | None, str]:
    """
    국내 주식 및 ETF의 실시간 시세를 수집합니다.
    
    수집 우선순위:
      1. 네이버 금융 공식 실시간 polling JSON API (초고속 ~0.05초 응답)
      2. 네이버 모바일 증권 API 보조
      3. NH투자증권 Open API (국내주식 시세)
      4. yfinance (.KS, .KQ 접미사 탐색)
      
    Args:
        ticker_code (str): 6자리 국내 종목코드 (예: '005930', '069500')
        
    Returns:
        Tuple[float | None, str]: (원화 현재가 또는 None, 시세 출처 또는 오류 사유)
    """
    # 1. 네이버 금융 공식 실시간 JSON API (초고속 0.05초 응답, HTML 스크래핑 파싱 실패 방지)
    try:
        url_polling = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{ticker_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url_polling, headers=headers, timeout=2)
        if res.status_code == 200:
            d = res.json()
            datas = d.get('datas', [])
            if datas:
                raw_val = datas[0].get('closePrice') or datas[0].get('nowPrice')
                if raw_val:
                    clean_p = float(str(raw_val).replace(',', '').strip())
                    if clean_p > 0:
                        return clean_p, "네이버 금융"
    except Exception:
        pass

    # 네이버 모바일 증권 API 보조
    try:
        url_m = f"https://m.stock.naver.com/api/stock/{ticker_code}/basic"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url_m, headers=headers, timeout=2)
        if res.status_code == 200:
            d = res.json()
            raw_val = d.get('closePrice') or d.get('nowPrice')
            if raw_val:
                clean_p = float(str(raw_val).replace(',', '').strip())
                if clean_p > 0:
                    return clean_p, "네이버 금융"
    except Exception:
        pass

    # 2. Namuh API 폴백
    try:
        price = nh_api_client.fetch_current_price(ticker_code, market="KR")
        if price is not None and price > 0:
            return price, "NH API"
    except Exception:
        pass

    # 3. yfinance 폴백 (fast_info 우선)
    try:
        for suffix in [".KS", ".KQ"]:
            t = yf.Ticker(f"{ticker_code}{suffix}")
            fast_p = getattr(t.fast_info, 'last_price', None)
            if fast_p is not None and not math.isnan(fast_p):
                return float(fast_p), "yfinance"
            hist = t.history(period="1d").dropna(subset=['Close'])
            if not hist.empty:
                return float(hist['Close'].iloc[-1]), "yfinance"
    except Exception as e:
        return None, f"yfinance 오류: {e}"
        
    return None, "시세를 찾을 수 없음"

def get_krx_gold_price(usd_krw: float = 1380.0) -> Tuple[float, str]:
    """
    KRX 금현물(종목코드: M04020000, 1g 기준)의 실시간 시세를 수집합니다.
    
    수집 우선순위:
      1. NH투자증권 Open API (증권사 KRX 금현물 호가 최우선)
      2. 네이버 모바일 증권 금 시세 JSON API
      3. 네이버 증권 PC 웹 페이지 스크래핑
      4. 글로벌 금선물(COMEX GC=F) 온스당 달러 시세의 1g 원화 환산 폴백
         (환산식: [온스당 USD * USD/KRW 환율] / 31.1034768g)
         
    Args:
        usd_krw (float): 달러-원 환율 (글로벌 선물 폴백 환산 시 사용)
        
    Returns:
        Tuple[float, str]: (1g당 원화 가격, 수집 출처 문자열)
    """
    # 1. Namuh API 시도
    try:
        price = nh_api_client.fetch_gold_price("M04020000")
        if price is not None and price > 0:
            return price, "NH API"
    except Exception:
        pass

    # 2. 네이버 모바일 증권 API (JSON 직접 반환)
    try:
        url_api = "https://api.stock.naver.com/marketindex/metals/M04020000"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url_api, headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            price_str = data.get('closePrice') or data.get('nowPrice')
            if price_str:
                clean_num = float(str(price_str).replace(',', '').strip())
                if clean_num > 0:
                    return clean_num, "네이버 금융"
    except Exception:
        pass

    # 3. 네이버 증권 PC 웹 폴백
    try:
        url_pc = 'https://finance.naver.com/marketindex/goldDetail.naver'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res_pc = requests.get(url_pc, headers=headers, timeout=3)
        tree_pc = html.fromstring(res_pc.content)
        elem_pc = tree_pc.xpath('//p[contains(@class, "no_today")]//span[@class="blind"]')
        if elem_pc:
            clean_val = float(elem_pc[0].text_content().replace(',', '').strip())
            if clean_val > 0:
                return clean_val, "네이버 금융"
    except Exception:
        pass

    # 4. 글로벌 금선물(GC=F) 야후 파이낸스 글로벌 클라우드 폴백
    try:
        ticker = yf.Ticker("GC=F")
        fast_oz = getattr(ticker.fast_info, 'last_price', None)
        if fast_oz is not None and not math.isnan(fast_oz):
            rate = float(usd_krw if usd_krw and usd_krw > 0 else 1380.0)
            return round((float(fast_oz) * rate) / 31.1034768, 0), "COMEX 금선물"
        hist = ticker.history(period="1d").dropna(subset=['Close'])
        if not hist.empty:
            price_usd_oz = float(hist['Close'].iloc[-1])
            if price_usd_oz > 0:
                rate = float(usd_krw if usd_krw and usd_krw > 0 else 1380.0)
                return round((price_usd_oz * rate) / 31.1034768, 0), "COMEX 금선물"
    except Exception:
        pass
        
    return 201620.0, "기본값"

def get_us_stock_price(ticker_symbol: str, usd_krw: float = 1380.0) -> Tuple[float | None, str]:
    """
    미국 주식 및 ETF의 실시간 시세를 수집하고 원화(KRW)로 환산하여 반환합니다.
    
    수집 우선순위:
      1. 네이버 해외증권 공식 JSON API (초고속 ~0.05초 응답)
         - 거래소 접미사 자동 시도 (예: VT -> VT, VT.O, VT.K, VT.N 순차 확인)
      2. NH투자증권 Open API (해외주식 실시간 호가)
      3. yfinance (fast_info / history)
      
    Args:
        ticker_symbol (str): 미국 티커 심볼 (예: 'VT', 'PDBC', 'QQQ')
        usd_krw (float): 현재 적용할 USD/KRW 환율 (기본값: 1380.0)
        
    Returns:
        Tuple[float | None, str]: (원화 환산 현재가 또는 None, 시세 출처 또는 오류 사유)
    """
    rate = float(usd_krw if usd_krw and usd_krw > 0 else 1380.0)
    
    # 1. 네이버 글로벌 증권 공식 API 최우선 (초고속 0.05초 응답)
    # VT, PDBC.O, SLYV.K 등 거래소 접미사 자동 시도
    candidates = [ticker_symbol]
    if '.' in ticker_symbol:
        base_sym = ticker_symbol.split('.')[0]
        candidates.extend([base_sym, f"{base_sym}.O", f"{base_sym}.K", f"{base_sym}.N"])
    else:
        candidates.extend([f"{ticker_symbol}.O", f"{ticker_symbol}.K", f"{ticker_symbol}.N"])

    seen = set()
    for sym_candidate in candidates:
        if sym_candidate in seen:
            continue
        seen.add(sym_candidate)
        try:
            url_nv = f"https://api.stock.naver.com/stock/{sym_candidate}/basic"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url_nv, headers=headers, timeout=2)
            if res.status_code == 200:
                d = res.json()
                raw_val = d.get('closePrice') or d.get('nowPrice')
                if raw_val:
                    usd_val = float(str(raw_val).replace(',', '').strip())
                    if usd_val > 0:
                        return round(usd_val * rate, 2), "네이버 금융"
        except Exception:
            pass

    # 2. Namuh API 폴백 (달러 시세 수취 후 실시간 환율 곱하여 원화 환산)
    try:
        usd_price = nh_api_client.fetch_current_price(ticker_symbol, market="US")
        if usd_price is not None and usd_price > 0:
            return round(usd_price * rate, 2), "NH API"
    except Exception:
        pass

    # 3. yfinance 폴백 (fast_info 우선)
    try:
        ticker = yf.Ticker(ticker_symbol)
        fast_price = getattr(ticker.fast_info, 'last_price', None)
        if fast_price is not None and not math.isnan(fast_price):
            return round(float(fast_price) * rate, 2), "yfinance"
            
        hist = ticker.history(period="1d").dropna(subset=['Close'])
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            return round(price * rate, 2), "yfinance"
            
    except Exception as e:
        return None, f"yfinance 오류: {e}"
    return None, "시세를 찾을 수 없음"

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

def _fetch_single_asset_price(asset: dict, usd_krw: float, now_str: str) -> dict:
    """
    개별 자산의 시장 유형(예금, 금현물, 국내주식, 미국주식)에 따라 적절한 수집기를 호출하고,
    원화 평가 시세와 메타데이터가 포함된 자산 가격 딕셔너리를 반환합니다.

    Args:
        asset (dict): 자산 정보 딕셔너리
        usd_krw (float): 현재 적용 환율
        now_str (str): 시세 수집 시각 문자열 ("YYYY-MM-DD HH:MM:SS")

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
    멀티스레드(ThreadPoolExecutor)를 통해 병렬로 고속 수집합니다.

    Args:
        assets (list): 조회할 자산 정보 딕셔너리 리스트
        usd_krw (float, optional): 적용할 USD/KRW 환율. None일 경우 실시간으로 즉시 조회

    Returns:
        Tuple[list, float]: (시세 정보가 보강된 자산 결과 리스트, 적용된 USD/KRW 환율)
    """
    if usd_krw is None:
        usd_krw, _ = get_exchange_rate_usd_krw()
        
    if not assets:
        return [], usd_krw

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 네이버 금융 고속 JSON API 최우선 활용 및 신속한 병렬 수집을 위해 동시 워커를 5개로 최적화
    max_workers = min(5, len(assets))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(lambda a: _fetch_single_asset_price(a, usd_krw, now_str), assets))
        
    return results, usd_krw
