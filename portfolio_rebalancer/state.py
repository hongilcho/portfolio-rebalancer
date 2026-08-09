import reflex as rx
import os
from dotenv import load_dotenv

load_dotenv()
from data.data_manager import init_db
from logic.price_fetcher import get_exchange_rate_usd_krw

class AppState(rx.State):
    """The central state for the application."""
    
    usd_krw: float = 1350.0  # Fallback
    rate_source: str = ""
    price_data: dict[str, dict] = {}
    password_correct: bool = False
    password_input: str = ""
    login_failed: bool = False
    
    def set_password_input(self, text: str):
        self.password_input = text
    
    def on_load(self):
        """Called when the app loads to initialize basic data."""
        # Ensure DB is initialized
        init_db()
        
        # Load exchange rate if not loaded
        if self.rate_source == "":
            rate, source = get_exchange_rate_usd_krw()
            self.usd_krw = rate
            self.rate_source = source
            
        if not self.price_data:
            from logic.price_fetcher import fetch_asset_prices
            from data.data_manager import get_all_assets
            assets = get_all_assets()
            results, _ = fetch_asset_prices(assets, self.usd_krw)
            self.price_data = {str(res['id']): res for res in results}

    def set_custom_usd_krw(self, val: str):
        try:
            val_f = float(val.replace(',', ''))
            self.usd_krw = val_f
            self.rate_source = "User Adjusted"
        except ValueError:
            pass

    def refresh_price_data(self):
        # Force refresh exchange rate
        rate, source = get_exchange_rate_usd_krw()
        self.usd_krw = rate
        self.rate_source = source
        
        # Force refresh price data
        from logic.price_fetcher import fetch_asset_prices
        from data.data_manager import get_all_assets
        assets = get_all_assets()
        results, _ = fetch_asset_prices(assets, self.usd_krw)
        
        # results is a list of dicts. We convert it to a dict mapped by string ID
        self.price_data = {str(res['id']): res for res in results}

    def check_password(self):
        """Check if the entered password is correct."""
        # We read from os.environ instead of st.secrets
        # Ensure APP_PASSWORD is set in environment or .env file
        correct_password = os.environ.get("APP_PASSWORD", "")
        
        if self.password_input == correct_password:
            # 1. Fetch prices synchronously so we don't show old data
            self.refresh_price_data()
            
            # 2. Allow access
            self.password_correct = True
            self.login_failed = False
            self.password_input = ""  # Clear it for security
            
            # 3. Tell dashboard to compute its rows
            from portfolio_rebalancer.pages.dashboard import DashboardState
            return DashboardState.load_dashboard_data
        else:
            self.password_correct = False
            self.login_failed = True
            
    def check_password_on_enter(self, key: str):
        if key == "Enter":
            return self.check_password()
            
    def logout(self):
        """Log the user out."""
        self.password_correct = False
