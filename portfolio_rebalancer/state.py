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
    
    def on_load(self):
        """Called when the app loads to initialize basic data."""
        # Ensure DB is initialized
        init_db()
        
        # Load exchange rate if not loaded
        if self.rate_source == "":
            rate, source = get_exchange_rate_usd_krw()
            self.usd_krw = rate
            self.rate_source = source

    def check_password(self):
        """Check if the entered password is correct."""
        # We read from os.environ instead of st.secrets
        # Ensure APP_PASSWORD is set in environment or .env file
        correct_password = os.environ.get("APP_PASSWORD", "")
        
        if self.password_input == correct_password:
            self.password_correct = True
            self.password_input = ""  # Clear it for security
        else:
            self.password_correct = False
            
    def logout(self):
        """Log the user out."""
        self.password_correct = False
