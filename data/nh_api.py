import os
import time
import requests
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class NamuhAPIClient:
    """
    NH투자증권 Namuh PLUG 오픈 API 연동 클래스
    """
    def __init__(self):
        try:
            self.app_key = st.secrets["nh_api"]["app_key"]
            self.app_secret = st.secrets["nh_api"]["app_secret"]
        except Exception:
            self.app_key = os.getenv("NAMUH_APP_KEY", "")
            self.app_secret = os.getenv("NAMUH_APP_SECRET", "")
            
        self.base_url = "https://api.nhplug.com:8443" 
        self.access_token = None
        self.token_expiry = 0

    def get_access_token(self):
        """
        OAuth 2.0 접근 토큰(Access Token) 발급
        """
        if time.time() < self.token_expiry and self.access_token:
            return self.access_token
            
        url = f"{self.base_url}/oauth2/token"
        headers = {"content-type": "application/x-www-form-urlencoded"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecretkey": self.app_secret,
            "scope": "oob"
        }
        
        try:
            res = requests.post(url, headers=headers, data=body, timeout=5, verify=False)
            if res.status_code != 200:
                print(f"Namuh API Token Error Details: {res.text}")
            res.raise_for_status()
            data = res.json()
            self.access_token = data.get("access_token")
            self.token_expiry = time.time() + int(data.get("expires_in", 86400)) - 60
            return self.access_token
        except Exception as e:
            print(f"Namuh API Token Error: {e}")
            return None

    def fetch_current_price(self, ticker: str, market: str = "KR"):
        """
        주식 현재가 조회 (KR/US 지원)
        """
        token = self.get_access_token()
        if not token:
            return None

        headers = {
            "content-type": "application/json;charset=utf-8",
            "Authorization": f"Bearer {token}"
        }
        
        try:
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
                price_str = data.get("Output_0", {}).get("trdprc", 0)
                return float(price_str)
                
        except Exception as e:
            print(f"Namuh API Price Fetch Error for {ticker}: {e}")
            return None

    def fetch_gold_price(self, ticker="M04020000"):
        """
        금현물 실시간 현재가 조회 (Namuh PLUG API)
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
        금현물 계좌 잔고 및 예수금 조회
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
        국내주식 잔고 및 예수금 조회
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
        해외주식 계좌 잔고 및 예수금 조회 (USD 기준)
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
            
            # 예수금
            out_0 = data.get("Output_0", {})
            deposit_usd = float(out_0.get("fc_dca", 0))
            
            # 해외주식 잔고
            out_1 = data.get("Output_1", [])
            holdings = []
            for item in out_1:
                qty = float(item.get("cns_bse_bnc_qty", 0))
                if qty > 0:
                    holdings.append({
                        "ticker": item.get("iem_cd", ""),
                        "name": item.get("iem_nm", ""),
                        "quantity": qty,
                        "avg_price": float(item.get("fc_phs_uit_pr", 0)),
                        "current_price": float(item.get("fc_sec_end_pr", 0))
                    })
                    
            return {
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
        국내주식 + 해외주식 잔고 통합 조회
        """
        dom_data, err_msg = self.fetch_account_balance(account_no)
        if not dom_data:
            return None, err_msg
            
        ov_data, ov_err = self.fetch_overseas_account_balance(account_no)
        # 해외주식 조회가 실패해도 국내주식이 성공했으면 에러내지 않고 진행할 수 있지만,
        # 완벽한 동기화를 위해 해외주식 API가 실패하면 전체 실패로 간주하거나 경고만 냄
        
        if ov_data:
            # 병합
            dom_data["deposit_usd"] = ov_data.get("deposit_usd", 0.0)
            dom_data["holdings"].extend(ov_data.get("holdings", []))
        else:
            # 해외주식 에러는 권한 문제일 수 있으므로 일단 무시(0 처리)
            dom_data["deposit_usd"] = 0.0
            
        return dom_data, None

nh_api_client = NamuhAPIClient()
