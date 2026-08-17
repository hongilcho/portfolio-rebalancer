import os
import toml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")

def load_secrets():
    secrets = {}
    if os.path.exists(SECRETS_PATH):
        try:
            with open(SECRETS_PATH, "r", encoding="utf-8") as f:
                secrets = toml.load(f)
        except Exception as e:
            print(f"Error loading secrets.toml: {e}")
            
    return secrets

secrets = load_secrets()

SUPABASE_URL = os.getenv("SUPABASE_URL", secrets.get("SUPABASE_URL", ""))
APP_PASSWORD = os.getenv("APP_PASSWORD", str(secrets.get("APP_PASSWORD", "1234")))

nh_sec = secrets.get("nh_api", {})
NAMUH_APP_KEY = os.getenv("NAMUH_APP_KEY", nh_sec.get("app_key", ""))
NAMUH_APP_SECRET = os.getenv("NAMUH_APP_SECRET", nh_sec.get("app_secret", ""))
