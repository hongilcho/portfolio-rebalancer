import pytest
from unittest.mock import patch
from logic.crypto_price_fetcher import get_crypto_prices
from backend.routers.crypto import get_crypto_summary, update_crypto_holdings, CryptoHoldingsUpdateRequest, CryptoHoldingItem

def test_crypto_prices_fetch():
    prices = get_crypto_prices()
    assert "BTC" in prices
    assert "ETH" in prices
    assert prices["BTC"]["price"] > 0
    assert prices["ETH"]["price"] > 0
    assert prices["BTC"]["symbol"] == "BTC"
    assert prices["ETH"]["symbol"] == "ETH"

def test_crypto_summary_multi_owner_calculation():
    # Mock holdings without touching real Supabase DB
    mock_holdings = [
        {"id": "crypto_hongil_btc", "owner": "홍일", "symbol": "BTC", "name": "비트코인", "quantity": 0.2, "avg_price": 90000000.0, "notes": "홍일 BTC"},
        {"id": "crypto_hongil_eth", "owner": "홍일", "symbol": "ETH", "name": "이더리움", "quantity": 1.0, "avg_price": 3500000.0, "notes": "홍일 ETH"},
        {"id": "crypto_yoona_btc", "owner": "윤아", "symbol": "BTC", "name": "비트코인", "quantity": 0.5, "avg_price": 80000000.0, "notes": "윤아 BTC"},
        {"id": "crypto_yoona_eth", "owner": "윤아", "symbol": "ETH", "name": "이더리움", "quantity": 3.0, "avg_price": 4000000.0, "notes": "윤아 ETH"},
    ]

    with patch("backend.routers.crypto.get_crypto_holdings", return_value=mock_holdings):
        summary = get_crypto_summary()
        assert "by_owner" in summary
        assert "홍일" in summary["by_owner"]
        assert "윤아" in summary["by_owner"]
        assert "crypto_assets_combined" in summary
        assert "crypto_total" in summary
        assert "owner_shares" in summary
        assert "combined_summary" in summary

        hongil = summary["by_owner"]["홍일"]
        yoona = summary["by_owner"]["윤아"]
        comb_list = summary["crypto_assets_combined"]
        cryp_total = summary["crypto_total"]

        # Verify combined quantities
        btc_comb = next(a for a in comb_list if a["symbol"] == "BTC")
        eth_comb = next(a for a in comb_list if a["symbol"] == "ETH")

        # Hongil 0.2 + Yoona 0.5 = 0.7 BTC
        assert round(btc_comb["quantity"], 4) == 0.7
        # Hongil (0.2 * 90M = 18M) + Yoona (0.5 * 80M = 40M) = 58M
        assert round(btc_comb["buy_amount"], 0) == 58000000.0
        # Weighted avg price = 58M / 0.7 ~= 82,857,142.85
        assert round(btc_comb["avg_price"], 0) == round(58000000.0 / 0.7, 0)

        # Hongil 1.0 + Yoona 3.0 = 4.0 ETH
        assert round(eth_comb["quantity"], 4) == 4.0
        # Hongil (1.0 * 3.5M) + Yoona (3.0 * 4.0M = 12M) = 15.5M
        assert round(eth_comb["buy_amount"], 0) == 15500000.0

        # Total buy should equal sum of hongil and yoona
        assert round(cryp_total["total_buy"], 0) == round(hongil["total_buy"] + yoona["total_buy"], 0)
        assert round(cryp_total["total_eval"], 0) == round(hongil["total_eval"] + yoona["total_eval"], 0)

        # Combined summary with portfolio
        comb = summary["combined_summary"]
        port = summary["portfolio_summary"]
        assert comb["total_eval"] == port["total_eval"] + cryp_total["total_eval"]
        assert comb["total_buy"] == port["total_buy"] + cryp_total["total_buy"]

def test_update_crypto_holdings_api():
    # Mock save_crypto_holding to verify API routing without modifying DB
    with patch("backend.routers.crypto.save_crypto_holding", return_value=(True, "저장 성공")) as mock_save:
        req = CryptoHoldingsUpdateRequest(holdings=[
            CryptoHoldingItem(owner="홍일", symbol="BTC", quantity=0.3, avg_price=95000000.0, notes="업데이트 홍일 BTC"),
            CryptoHoldingItem(owner="윤아", symbol="BTC", quantity=0.5, avg_price=80000000.0, notes="윤아 BTC 유지")
        ])
        res = update_crypto_holdings(req)
        assert res["success"] is True
        assert res["updated_count"] == 2
        assert mock_save.call_count == 2
