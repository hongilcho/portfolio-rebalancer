import pytest
from logic.crypto_price_fetcher import get_crypto_prices
from data.data_manager import get_crypto_holdings, save_crypto_holding
from backend.routers.crypto import get_crypto_summary, update_crypto_holdings, CryptoHoldingsUpdateRequest, CryptoHoldingItem

def test_crypto_prices_fetch():
    prices = get_crypto_prices()
    assert "BTC" in prices
    assert "ETH" in prices
    assert prices["BTC"]["price"] > 0
    assert prices["ETH"]["price"] > 0
    assert prices["BTC"]["symbol"] == "BTC"
    assert prices["ETH"]["symbol"] == "ETH"

def test_crypto_holdings_crud():
    # Save BTC holding
    success, msg = save_crypto_holding("BTC", 0.5, 80000000.0, "테스트 비트코인")
    assert success is True

    # Save ETH holding
    success, msg = save_crypto_holding("ETH", 3.0, 4000000.0, "테스트 이더리움")
    assert success is True

    holdings = get_crypto_holdings()
    h_map = {h['symbol']: h for h in holdings}
    
    assert h_map['BTC']['quantity'] == 0.5
    assert h_map['BTC']['avg_price'] == 80000000.0
    assert h_map['ETH']['quantity'] == 3.0
    assert h_map['ETH']['avg_price'] == 4000000.0

def test_crypto_summary_calculation():
    summary = get_crypto_summary()
    assert "crypto_assets" in summary
    assert "crypto_total" in summary
    assert "portfolio_summary" in summary
    assert "combined_summary" in summary

    # Verify combined calculation
    comb = summary["combined_summary"]
    port = summary["portfolio_summary"]
    cryp = summary["crypto_total"]

    assert comb["total_eval"] == port["total_eval"] + cryp["total_eval"]
    assert comb["total_buy"] == port["total_buy"] + cryp["total_buy"]
    assert round(comb["portfolio_weight_pct"] + comb["crypto_weight_pct"], 1) == 100.0 or comb["total_eval"] == 0
