import yfinance as yf
import requests
import re
from datetime import datetime
from lxml import html
import urllib3
import streamlit as st
import math
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_exchange_rate_usd_krw():
    """USD/KRW 실시간 환율 수집 (yfinance primary, Naver Finance fallback)"""
    try:
        ticker = yf.Ticker("KRW=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            rate = float(hist['Close'].iloc[-1])
            return round(rate, 2), "yfinance"
    except Exception:
        pass
    
    # Naver Finance fallback
    try:
        url = "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'today.*?<span class="blind">([0-9,.]+)\s*</span>', res.text, re.DOTALL)
        if match:
            rate = float(match.group(1).replace(',', ''))
            return round(rate, 2), "네이버 금융"
    except Exception:
        pass
    
    return 1380.0, "기본값(기본 1380원)"

def get_kr_stock_price(ticker_code):
    """국내 주식/ETF 실시간 시세 수집 (네이버 금융 최우선 -> yfinance 폴백)"""
    # 1. 네이버 금융 시도 (완벽한 실시간 시세)
    try:
        url = f'https://finance.naver.com/item/main.naver?code={ticker_code}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<dd>현재가\s+([0-9,]+)', res.text)
        if match:
            price = float(match.group(1).replace(',', ''))
            return price, None
    except Exception as e:
        pass # 네이버 조회 실패 시 yfinance 폴백
        
    # 2. yfinance 폴백
    try:
        import yfinance as yf
        # KOSPI 종목 시도 (.KS)
        ticker_ks = yf.Ticker(f"{ticker_code}.KS")
        hist_ks = ticker_ks.history(period="5d").dropna(subset=['Close'])
        if not hist_ks.empty:
            return float(hist_ks['Close'].iloc[-1]), None
            
        # KOSDAQ 종목 시도 (.KQ)
        ticker_kq = yf.Ticker(f"{ticker_code}.KQ")
        hist_kq = ticker_kq.history(period="5d").dropna(subset=['Close'])
        if not hist_kq.empty:
            return float(hist_kq['Close'].iloc[-1]), None
            
    except Exception as e:
        return None, f"yfinance 폴백 조회 오류: {e}"
        
    return None, "시세를 찾을 수 없습니다."

def get_krx_gold_price():
    """KRX 금현물 실시간 시세 수집 (네이버 금융 모바일 M04020000)"""
    try:
        url = 'https://m.stock.naver.com/marketindex/metals/M04020000'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5, verify=False)
        tree = html.fromstring(res.content)
        element = tree.xpath('//*[@id="content"]/div[1]/div[2]/div[2]/strong')
        if element:
            price_text = element[0].text_content().strip()
            # Extract only digits and decimal point
            price_clean = re.sub(r'[^0-9.]', '', price_text)
            if price_clean:
                return float(price_clean), None
    except Exception as e:
        return None, f"금 시세 크롤링 오류: {e}"
    return None, "금 시세를 찾을 수 없습니다."

def get_us_stock_price(ticker_symbol):
    """미국 주식/ETF 실시간 시세 수집 (yfinance)"""
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # 1. 시도: fast_info에서 최신 실시간 가격 가져오기 (NaN 버그 우회 및 가장 최신)
        try:
            last_price = getattr(ticker.fast_info, 'last_price', None)
            if last_price is not None and not math.isnan(last_price):
                return float(last_price), None
        except Exception:
            pass
            
        # 2. 폴백: history에서 NaN 제외한 가장 최근 종가 가져오기
        hist = ticker.history(period="5d").dropna(subset=['Close'])
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            return price, None
            
    except Exception as e:
        return None, str(e)
    return None, "시세를 찾을 수 없습니다."

@st.cache_data(ttl=60, show_spinner=False)
def fetch_asset_prices(assets, usd_krw=None):
    """자산 목록 전체의 실시간 시세 및 원화 환산 가격 일괄 수집"""
    if usd_krw is None:
        usd_krw, _ = get_exchange_rate_usd_krw()
        
    results = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for asset in assets:
        market = asset['market']
        ticker = asset['ticker']
        
        if not ticker or ticker.strip() == '없음' or ticker.strip() == '-':
            if '금' in asset['name'] or 'Gold' in asset['name']:
                raw_price, err = get_krx_gold_price()
                if raw_price is not None:
                    price_krw = raw_price
                    price_usd = raw_price / usd_krw if usd_krw else 0
                    status = "정상 (크롤링)"
                else:
                    price_krw = 0.0
                    price_usd = 0.0
                    status = f"오류: {err}"
            else:
                raw_price = 0.0
                price_krw = 0.0
                price_usd = 0.0
                status = "수동 입력 필요 (Ticker 없음)"
        elif market == 'KR':
            raw_price, err = get_kr_stock_price(ticker)
            if raw_price is not None:
                price_krw = raw_price
                price_usd = raw_price / usd_krw if usd_krw else 0
                status = "정상"
            else:
                price_krw = 0.0
                price_usd = 0.0
                status = f"오류: {err}"
        else: # US
            raw_price, err = get_us_stock_price(ticker)
            if raw_price is not None:
                price_usd = raw_price
                price_krw = raw_price * usd_krw
                status = "정상"
            else:
                price_usd = 0.0
                price_krw = 0.0
                status = f"오류: {err}"
                
        results.append({
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
            "updated_at": now_str
        })
        
    return results, usd_krw
