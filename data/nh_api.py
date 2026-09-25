"""
NH투자증권 Namuh PLUG Open API 연동 클라이언트 모듈
===================================================
NH투자증권(나무증권)의 Open API와 통신하여 실시간 국내/해외 주식 시세,
KRX 금현물 시세, 계좌별 예수금 및 잔고를 안전하게 조회합니다.

주요 특징:
1. OAuth 2.0 Access Token 관리 (24시간 유효기간 캐싱 및 스레드 안전성 보장)
2. API 요청 쓰로틀링(_throttle): 초당 요청 제한(429)을 방지하기 위한 최소 250ms 호출 간격 보장
3. 장애 시 60초 쿨다운(cooldown) 적용으로 시스템 블로킹 방지 및 대체 수집기 즉시 전환 유도
"""

import os
import time
import requests
import urllib3
import threading
from backend.config import NAMUH_APP_KEY, NAMUH_APP_SECRET

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class NamuhAPIClient:
    """
    NH투자증권 Namuh PLUG 오픈 API 클라이언트
    
    인증 토큰 발급, 시세 조회, 계좌 잔고 동기화 기능을 제공합니다.
    """
    def __init__(self):
        self.app_key = os.getenv("NAMUH_APP_KEY") or NAMUH_APP_KEY
        self.app_secret = os.getenv("NAMUH_APP_SECRET") or NAMUH_APP_SECRET
            
        self.base_url = "https://api.nhplug.com:8443" 
        self.access_token = None
        self.token_expiry = 0
        self.token_cooldown = 0
        self._lock = threading.Lock()
        self._call_lock = threading.Lock()
        self._last_call_time = 0.0
        self._min_call_interval = 0.25  # NH API 429(거래건수 초과) 방지용 250ms 페이싱

    def _throttle(self):
        """
        API 호출 간 최소 대기 시간(250ms)을 보장하여 초당 거래건수 초과(HTTP 429)를 원천 차단합니다.
        """
        with self._call_lock:
            now = time.time()
            elapsed = now - self._last_call_time
            if elapsed < self._min_call_interval:
                time.sleep(self._min_call_interval - elapsed)
            self._last_call_time = time.time()

    def get_access_token(self) -> str | None:
        """
        OAuth 2.0 접근 토큰(Access Token)을 발급받거나 기존 유효 토큰을 반환합니다.
        
        - 토큰 유효 시간(약 24시간) 동안 메모리에 캐싱됩니다.
        - 토큰 발급 실패 또는 API 호출 제한 시 60초간 쿨다운을 적용하여
          지연 없이 대체 소스(네이버 금융 등)로 폴백할 수 있도록 합니다.
          
        Returns:
            str | None: 발급된 Bearer 토큰 문자열, 실패 시 None
        """
        with self._lock:
            now = time.time()
            if now < self.token_expiry and self.access_token:
                return self.access_token
            if now < self.token_cooldown:
                return None
                
            url = f"{self.base_url}/oauth2/token"
            headers = {"content-type": "application/x-www-form-urlencoded"}
            body = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecretkey": self.app_secret,
                "scope": "oob"
            }
            
            try:
                res = requests.post(url, headers=headers, data=body, timeout=3, verify=False)
                if res.status_code != 200:
                    print(f"Namuh API Token Error Details: {res.text}")
                    # 호출 제한(429/403 등) 시 60초간 재요청 방지하여 대체 경로(Naver/yfinance) 즉시 진행
                    self.token_cooldown = now + 60.0
                    return None
                res.raise_for_status()
                data = res.json()
                self.access_token = data.get("access_token")
                self.token_expiry = now + int(data.get("expires_in", 86400)) - 60
                self.token_cooldown = 0
                return self.access_token
            except Exception as e:
                print(f"Namuh API Token Error: {e}")
                self.token_cooldown = now + 60.0
                return None

    def fetch_current_price(self, ticker: str, market: str = "KR") -> float | None:
        """
        국내 또는 미국 주식/ETF의 실시간 현재가를 조회합니다.

        Args:
            ticker (str): 종목 코드 (국내 6자리 또는 미국 티커 심볼)
            market (str): 시장 구분 ("KR" 또는 "US", 기본값 "KR")

        Returns:
            float | None: 조회된 현재가(원화 또는 달러), 실패 시 None
        """
        token = self.get_access_token()
        if not token:
            return None

        headers = {
            "content-type": "application/json;charset=utf-8",
            "Authorization": f"Bearer {token}"
        }
        
        try:
            self._throttle()
            if market == "KR":
                url = f"{self.base_url}/krstock/quote/v1/currentPrice"
                body = {
                    "Input_0": {
                        "market_cd": "KRX",
                        "iem_cd": ticker
                    }
                }
                res = requests.post(url, headers=headers, json=body, timeout=5, verify=False)
                if res.status_code != 200:
                    print(f"Namuh API KR Price Fetch Error for {ticker}: {res.text}")
                res.raise_for_status()
                data = res.json()
                price_str = data.get("Output_0", {}).get("stck_prpr", 0)
                return float(price_str)
                
            else: # US
                url = f"{self.base_url}/gbstock/quote/v1/current"
                body = {
                    "Input_0": {
                        "iem_cd": ticker
                    }
                }
                res = requests.post(url, headers=headers, json=body, timeout=5, verify=False)
                if res.status_code != 200:
                    print(f"Namuh API US Price Fetch Error for {ticker}: {res.text}")
                res.raise_for_status()
                data = res.json()
                out_0 = data.get("Output_0", {})
                trdprc = float(out_0.get("trdprc", 0))
                return trdprc if trdprc > 0 else None
                
        except Exception as e:
            print(f"Namuh API Price Fetch Error for {ticker}: {e}")
            return None

    def fetch_gold_price(self, ticker: str = "M04020000") -> float | None:
        """
        KRX 금현물 종목의 실시간 현재가(1g 기준 원화)를 조회합니다.

        Args:
            ticker (str): 금현물 종목 코드 (기본값: 'M04020000', 금 99.99_1Kg)

        Returns:
            float | None: 1g당 현재가(원화), 실패 시 None
        """
        token = self.get_access_token()
        if not token:
            return None
            
        url = f"{self.base_url}/krgold/quote/v1/goldCurrent"
        headers = {
            "content-type": "application/json;charset=utf-8",
            "Authorization": f"Bearer {token}"
        }
        body = {
            "Input_0": {
                "iem_cd": ticker
            }
        }
        
        try:
            self._throttle()
            res = requests.post(url, headers=headers, json=body, timeout=5, verify=False)
            if res.status_code != 200:
                print(f"Namuh API Gold Price Fetch Error for {ticker}: {res.text}")
            res.raise_for_status()
            data = res.json()
            
            price_str = data.get("Output_0", {}).get("stck_prpr", 0)
            return float(price_str)
        except Exception as e:
            print(f"Namuh API Gold Price Fetch Error for {ticker}: {e}")
            return None

    def fetch_gold_account_balance(self, account_no: str):
        """
        NH 금현물 전용 계좌의 예수금 및 금 보유 잔고를 조회합니다.

        Args:
            account_no (str): NH증권 금현물 계좌번호

        Returns:
            Tuple[dict | None, str | None]: (예수금 및 보유현황 딕셔너리, 에러메시지)
        """
        token = self.get_access_token()
        if not token:
            return None, "토큰 발급 실패"
            
        url = f"{self.base_url}/krgold/inquiry/v1/goldDepositAndBalance"
        headers = {
            "content-type": "application/json;charset=utf-8",
            "Authorization": f"Bearer {token}"
        }
        body = {
            "Input_0": {
                "act_no": str(account_no).replace("-", "")
            }
        }
        
        try:
            res = requests.post(url, headers=headers, json=body, timeout=5, verify=False)
            if res.status_code != 200:
                print(f"Namuh API Gold Account Balance Fetch Error for {account_no}: {res.text}")
            res.raise_for_status()
            data = res.json()
            
            # 예수금 (dca)
            out_0 = data.get("Output_0", {})
            deposit = float(out_0.get("dca", 0))
            
            # 금 잔고
            out_1 = data.get("Output_1", [])
            holdings = []
            for item in out_1:
                # 종목명, 종목코드, 수량(itg_bnc_qty), 평단가(phs_pr), 현재가(now_pr)
                qty = float(item.get("itg_bnc_qty", 0))
                if qty > 0:
                    holdings.append({
                        "ticker": item.get("iem_cd", ""),
                        "name": item.get("iem_nm", ""),
                        "quantity": qty,
                        "avg_price": float(item.get("phs_pr", 0)),
                        "current_price": float(item.get("now_pr", 0))
                    })
                    
            return {
                "deposit_krw": deposit,
                "holdings": holdings
            }, None
            
        except Exception as e:
            err_msg = str(e)
            if 'res' in locals() and res.status_code != 200:
                err_msg = res.text
            print(f"Namuh API Gold Account Balance Fetch Error for {account_no}: {err_msg}")
            return None, err_msg

    def fetch_exchange_rate(self, currency="USD"):
        """
        실시간 환율 조회 (API 미제공으로 인한 fallback 유도)
        """
        return None

    def fetch_account_balance(self, account_no: str):
        """
        국내주식 위탁 계좌의 체결 기준 잔고 및 원화 예수금을 조회합니다.

        Args:
            account_no (str): 조회할 계좌번호 (하이픈 포함/제외 무관)

        Returns:
            Tuple[dict | None, str | None]: (원화예수금 및 보유종목 리스트, 에러메시지)
        """
        token = self.get_access_token()
        if not token:
            return None
            
        url = f"{self.base_url}/krstock/inquiry/v1/balance"
        headers = {
            "content-type": "application/json;charset=utf-8",
            "Authorization": f"Bearer {token}"
        }
        body = {
            "Input_0": {
                "act_no": str(account_no).replace("-", ""),
                "bnc_bse_cd": "1", # 1: 체결기준
                "ltg_aot_dit_cd": "9", # 9: 전체
                "aet_bse": "2", # 2: 총자산
                "qut_dit_cd": "UNT" # 통합시세
            }
        }
        
        try:
            res = requests.post(url, headers=headers, json=body, timeout=5, verify=False)
            if res.status_code != 200:
                print(f"Namuh API Account Balance Fetch Error for {account_no}: {res.text}")
            res.raise_for_status()
            data = res.json()
            
            # 예수금 (dca)
            out_0 = data.get("Output_0", {})
            deposit = float(out_0.get("dca", 0))
            
            # 주식 잔고
            out_1 = data.get("Output_1", [])
            holdings = []
            for item in out_1:
                # 종목명, 종목코드, 수량(itg_bnc_qty), 평단가(phs_pr), 현재가(now_pr)
                qty = float(item.get("itg_bnc_qty", 0))
                if qty > 0:
                    holdings.append({
                        "ticker": item.get("iem_cd", ""),
                        "name": item.get("iem_nm", ""),
                        "quantity": qty,
                        "avg_price": float(item.get("phs_pr", 0)),
                        "current_price": float(item.get("now_pr", 0))
                    })
                    
                # return tuple
            return {
                "deposit_krw": deposit,
                "holdings": holdings
            }, None
            
        except Exception as e:
            err_msg = str(e)
            if 'res' in locals() and res.status_code != 200:
                err_msg = res.text
            print(f"Namuh API Account Balance Fetch Error for {account_no}: {err_msg}")
            return None, err_msg

    def fetch_overseas_account_balance(self, account_no: str):
        """
        해외(미국) 주식 위탁 계좌의 잔고 및 외화(USD)/원화 예수금을 조회합니다.

        Args:
            account_no (str): 조회할 계좌번호 (하이픈 포함/제외 무관)

        Returns:
            Tuple[dict | None, str | None]: (원화/외화 예수금 및 보유종목 리스트, 에러메시지)
        """
        token = self.get_access_token()
        if not token:
            return None, "토큰 발급 실패"
            
        url = f"{self.base_url}/gbstock/inquiry/v1/balance"
        headers = {
            "content-type": "application/json;charset=utf-8",
            "Authorization": f"Bearer {token}"
        }
        body = {
            "Input_0": {
                "act_no": str(account_no).replace("-", ""),
                "qut_iqr_dit_cd": "9",
                "fc_sec_trd_nat_cd": "200", # 200: 미국
                "cur_cd": "USD",
                "xns_dit_cd": "0"
            }
        }
        
        try:
            res = requests.post(url, headers=headers, json=body, timeout=5, verify=False)
            if res.status_code != 200:
                print(f"Namuh API Overseas Balance Error for {account_no}: {res.text}")
            res.raise_for_status()
            data = res.json()
            
            # 예수금 (원화 예수금 krw_dca, 외화 예수금 fc_dca)
            out_0 = data.get("Output_0", {})
            deposit_krw = float(out_0.get("krw_dca", 0))
            deposit_usd = float(out_0.get("fc_dca", 0))
            
            # 해외주식 잔고 (원화 평단가 phs_uit_pr, 원화 현재가 end_pr)
            out_1 = data.get("Output_1", [])
            holdings = []
            for item in out_1:
                qty = float(item.get("cns_bse_bnc_qty", 0))
                if qty > 0:
                    holdings.append({
                        "ticker": item.get("iem_cd", ""),
                        "name": item.get("iem_nm", ""),
                        "quantity": qty,
                        "avg_price": float(item.get("phs_uit_pr", 0)),
                        "current_price": float(item.get("end_pr", 0))
                    })
                    
            return {
                "deposit_krw": deposit_krw,
                "deposit_usd": deposit_usd,
                "holdings": holdings
            }, None
            
        except Exception as e:
            err_msg = str(e)
            if 'res' in locals() and res.status_code != 200:
                err_msg = res.text
            print(f"Namuh API Overseas Balance Error for {account_no}: {err_msg}")
            return None, err_msg
            
    def fetch_full_account_balance(self, account_no: str):
        """
        국내주식 잔고와 해외(미국)주식 잔고를 동시에 조회하여 통합 병합된 잔고 데이터를 반환합니다.

        Args:
            account_no (str): 조회할 계좌번호

        Returns:
            Tuple[dict | None, str | None]: (통합 예수금 및 보유종목 리스트, 에러메시지)
        """
        dom_data, err_msg = self.fetch_account_balance(account_no)
        if not dom_data:
            return None, err_msg
            
        ov_data, ov_err = self.fetch_overseas_account_balance(account_no)
        if ov_data:
            # 병합
            dom_data["deposit_krw"] = dom_data.get("deposit_krw", 0.0) + ov_data.get("deposit_krw", 0.0)
            dom_data["deposit_usd"] = ov_data.get("deposit_usd", 0.0)
            dom_data["holdings"].extend(ov_data.get("holdings", []))
        else:
            dom_data["deposit_usd"] = 0.0
            
        return dom_data, None

nh_api_client = NamuhAPIClient()
