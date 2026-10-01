"""
백엔드 환경설정 및 비밀값(Secrets) 로더 모듈
============================================
.env 파일, 시스템 환경변수, 또는 .streamlit/secrets.toml 파일로부터
데이터베이스 연결 URL(SUPABASE_URL), 관리자 비밀번호(APP_PASSWORD),
NH투자증권 Open API 키(NAMUH_APP_KEY, NAMUH_APP_SECRET)를 안전하게 로드합니다.
"""

import os
import toml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
ENV_PATH = os.path.join(BASE_DIR, ".env")

def load_config():
    """
    환경 변수 및 설정 파일 로드:
    1. .env 파일 (우선순위 1)
    2. 시스템 환경 변수 (os.getenv)
    3. .streamlit/secrets.toml (하위 호환 fallback)
    """
    try:
        from dotenv import load_dotenv
        if os.path.exists(ENV_PATH):
            load_dotenv(ENV_PATH)
        else:
            load_dotenv()
    except ImportError:
        pass
        
    secrets = {}
    if os.path.exists(SECRETS_PATH):
        try:
            with open(SECRETS_PATH, "r", encoding="utf-8") as f:
                secrets = toml.load(f)
        except Exception as e:
            print(f"Error loading secrets.toml: {e}")

    def clean_val(val):
        if not val:
            return ""
        s = str(val).strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        return s

    supabase_url = clean_val(os.getenv("SUPABASE_URL") or secrets.get("SUPABASE_URL", ""))
    app_password = clean_val(os.getenv("APP_PASSWORD") or secrets.get("APP_PASSWORD", "1234")) or "1234"
    
    nh_sec = secrets.get("nh_api", {})
    namuh_app_key = clean_val(os.getenv("NAMUH_APP_KEY") or nh_sec.get("app_key", ""))
    namuh_app_secret = clean_val(os.getenv("NAMUH_APP_SECRET") or nh_sec.get("app_secret", ""))

    return supabase_url, app_password, namuh_app_key, namuh_app_secret

SUPABASE_URL, APP_PASSWORD, NAMUH_APP_KEY, NAMUH_APP_SECRET = load_config()
