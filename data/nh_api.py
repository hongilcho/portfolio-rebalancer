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

    def fetch_exchange_rate(self, currency="USD"):
        """
        실시간 환율 조회 (API 미제공으로 인한 fallback 유도)
        """
        return None

nh_api_client = NamuhAPIClient()
