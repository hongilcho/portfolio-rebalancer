import yfinance as yf
import requests
import re
from datetime import datetime
from lxml import html
import urllib3
import math
import concurrent.futures
from data.nh_api import nh_api_client
from typing import Tuple

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_exchange_rate_usd_krw():
    """USD/KRW 실시간 환율 수집 (Namuh API 최우선, yfinance/Naver fallback)"""
    # 1. Namuh API 시도
    try:
        rate = nh_api_client.fetch_exchange_rate("USD")
        if rate is not None and rate > 0:
            return round(rate, 2), "Namuh API"
    except Exception:
        pass

    # 2. yfinance fallback
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
    
    # 3. Naver Finance fallback
    try:
        url = "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        match = re.search(r'today.*?<span class="blind">([0-9,.]+)\s*</span>', res.text, re.DOTALL)
        if match:
            clean_str = match.group(1).replace(',', '')
            return round(float(clean_str), 2), "네이버 금융"
            
        match_simple = re.search(r'class="value">([0-9,.]+)<', res.text)
        if match_simple:
            clean_str = match_simple.group(1).replace(',', '')
            return round(float(clean_str), 2), "네이버 금융"
    except Exception:
        pass
        
    return 1380.0, "기본값(기본 1380원)"

def get_kr_stock_price(ticker_code):
    """국내 주식/ETF 실시간 시세 수집 (Namuh API 최우선 -> 네이버 금융 -> yfinance 폴백)"""
    # 1. Namuh API 시도
    try:
        price = nh_api_client.fetch_current_price(ticker_code, market="KR")
        if price is not None and price > 0:
            return price, "NH API"
    except Exception:
        pass

    # 2. 네이버 금융 폴백 (XPath & Regex - 초고속 HTML 파싱)
    try:
        url = f'https://finance.naver.com/item/main.naver?code={ticker_code}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        tree = html.fromstring(res.content)
        blind_elem = tree.xpath('//p[contains(@class, "no_today")]//span[@class="blind"]')
        if blind_elem:
            val_str = blind_elem[0].text_content().replace(',', '').strip()
            if val_str.isdigit():
                return float(val_str), "네이버 금융"
        
        match = re.search(r'<dd>현재가\s+([0-9,]+)', res.text)
        if match:
            price = float(match.group(1).replace(',', ''))
            return price, "네이버 금융"
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

def get_krx_gold_price(usd_krw: float = 1380.0):
    """KRX 금현물 실시간 시세 수집 (Namuh API -> 네이버 공식 금 시세 API -> 글로벌 금선물 GC=F 폴백)"""
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

def get_us_stock_price(ticker_symbol, usd_krw: float = 1380.0):
    """미국 주식/ETF 실시간 시세 수집 (Namuh API 달러 현재가 수취 -> 실시간 환율 usd_krw 곱하여 원화 환산)"""
    rate = float(usd_krw if usd_krw and usd_krw > 0 else 1380.0)
    
    # 1. Namuh API 시도 (달러 시세 수취 후 실시간 환율 곱하여 원화 환산)
    try:
        usd_price = nh_api_client.fetch_current_price(ticker_symbol, market="US")
        if usd_price is not None and usd_price > 0:
            return round(usd_price * rate, 2), "NH API"
    except Exception:
        pass

    # 2. yfinance 폴백 (fast_info 우선)
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
    정기예금의 일할 세후 누적이자 가산 현재가 계산
    Returns:
        current_price, accrued_days, gross_interest, net_interest
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

def fetch_asset_prices(assets, usd_krw=None):
    """자산 목록 전체의 실시간 시세 및 원화 환산 가격 멀티스레드 병렬 수집"""
    if usd_krw is None:
        usd_krw, _ = get_exchange_rate_usd_krw()
        
    if not assets:
        return [], usd_krw

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # I/O 바운드 작업이므로 ThreadPoolExecutor를 통한 10개 스레드 동시 병렬 요청
    max_workers = min(12, len(assets))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(lambda a: _fetch_single_asset_price(a, usd_krw, now_str), assets))
        
    return results, usd_krw
